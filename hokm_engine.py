"""Four-player partnership Hokm, server-authoritative and JSON serializable.

Seats 0 (human), 1 (right), 2 (AI partner), 3 (left); play passes to the right.
Standard rules: https://www.jahanshiri.ir/cardgames/en/hokm
Hakem / partner are drawn with aces and reseated before a fresh shuffle.
Only Hakem receives five cards before trump; finish the 5/4/4 deal afterwards.
Seven tricks wins a hand; ordinary / Kot / Hakem Kot score 1 / 2 / 3.
Trick and hand boundaries require acknowledgement, preserving the four played cards.
AI receives an observation containing its own hand and public information only.
"""
import copy
import random

SUITS = ('C', 'D', 'H', 'S')
RANKS = ('2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A')
ALL_CARDS = tuple(s + r for s in SUITS for r in RANKS)
VALUES = {r: i + 2 for i, r in enumerate(RANKS)}
LEVELS = ('easy', 'medium', 'hard')
HUMAN = 0
TARGET = 7
SR = random.SystemRandom()


class IllegalMove(ValueError):
    pass


def _draw_roles(rng):
    deck = list(ALL_CARDS)
    rng.shuffle(deck)
    reveals, aces, seat = [], [], 0
    for card in deck:
        while seat in aces:
            seat = (seat + 1) % 4
        reveals.append({'seat': seat, 'card': card})
        if card[1:] == 'A':
            aces.append(seat)
            if len(aces) == 2:
                break
        seat = (seat + 1) % 4
    # Preserve human seat 0; place the two drawn partners opposite one another.
    partner = aces[1] if aces[0] == 0 else aces[0] if aces[1] == 0 else next(i for i in range(1, 4) if i not in aces)
    opponents = [i for i in range(1, 4) if i != partner]
    identities = [0, opponents[0], partner, opponents[1]]
    mapping = {identity: seat for seat, identity in enumerate(identities)}
    return mapping[aces[0]], identities, [{**r, 'seat': mapping[r['seat']]} for r in reveals]


def _deal_hand(st, rng):
    deck = list(ALL_CARDS)
    rng.shuffle(deck)
    st.update(round=st['round'] + 1, phase='choose_trump', trump=None,
              dealer=(st['hakem'] - 1) % 4, turn=st['hakem'], leader=st['hakem'],
              deck=deck, hands=[[], [], [], []], tricks=[0, 0], trick=[],
              trick_history=[], voids=[[], [], [], []], last_trick=None)
    st['hands'][st['hakem']] = [st['deck'].pop() for _ in range(5)]


def new_game(level='medium', rng=None):
    if level not in LEVELS:
        raise ValueError('bad level')
    rng = rng or SR
    hakem, identities, reveals = _draw_roles(rng)
    st = dict(level=level, scores=[0, 0], target_score=TARGET, round=0, hakem=hakem,
              identities=identities, selection=reveals, round_log=[], finished=False,
              winner=None, draw=False, moves_count=0, events=[])
    _deal_hand(st, rng)
    return st


def choose_trump(state, seat, suit):
    if (state['finished'] or state['phase'] != 'choose_trump'
            or type(seat) is not int or seat != state['hakem']):
        raise IllegalMove('not_hakem')
    if not isinstance(suit, str) or suit not in SUITS:
        raise IllegalMove('invalid_suit')
    st = copy.deepcopy(state)
    st['trump'] = suit
    order = [(st['hakem'] + i) % 4 for i in range(4)]
    # Finish the first five-card packets, then two rounds of four-card packets.
    for p in order[1:]:
        st['hands'][p] = [st['deck'].pop() for _ in range(5)]
    for _ in range(2):
        for p in order:
            st['hands'][p] += [st['deck'].pop() for _ in range(4)]
    st['phase'] = 'play'
    st['events'].append({'type': 'trump', 'seat': seat, 'suit': suit})
    return st


def legal_cards(state, seat=None):
    seat = state['turn'] if seat is None else seat
    if (state['finished'] or state['phase'] != 'play' or type(seat) is not int
            or seat not in range(4) or seat != state['turn']):
        return []
    hand = state['hands'][seat]
    lead = state['trick'][0]['card'][0] if state['trick'] else None
    following = [c for c in hand if c[0] == lead]
    return list(following or hand)


def trick_winner(trick, trump):
    if not trick:
        raise ValueError('empty trick')
    led = trick[0]['card'][0]
    def power(play):
        c = play['card']
        return (2 if c[0] == trump else 1 if c[0] == led else 0, VALUES[c[1:]])
    return max(trick, key=power)['seat']


def hand_points(tricks, hakem):
    """Return winning team and awarded match points at the seven-trick boundary."""
    if max(tricks) != 7:
        raise ValueError('hand not decided')
    winner = 0 if tricks[0] == 7 else 1
    points = 1 if tricks[1 - winner] else 2 if winner == hakem % 2 else 3
    return winner, points


def _play(st, seat, card):
    if not isinstance(card, str) or card not in legal_cards(st, seat):
        raise IllegalMove('illegal_card')
    if st['trick'] and card[0] != st['trick'][0]['card'][0]:
        lead = st['trick'][0]['card'][0]
        if lead not in st['voids'][seat]:
            st['voids'][seat].append(lead)
    st['hands'][seat].remove(card)
    st['trick'].append({'seat': seat, 'card': card})
    st['events'].append({'type': 'play', 'seat': seat, 'card': card})
    st['moves_count'] += 1
    if len(st['trick']) < 4:
        st['turn'] = (seat + 1) % 4
        return
    winner = trick_winner(st['trick'], st['trump'])
    st['tricks'][winner % 2] += 1
    entry = {'cards': copy.deepcopy(st['trick']), 'winner': winner, 'number': len(st['trick_history']) + 1}
    st['trick_history'].append(entry)
    st['last_trick'] = entry
    st['turn'] = None
    st['phase'] = 'trick_end'
    st['events'].append({'type': 'trick_end', 'winner': winner})
    if max(st['tricks']) == 7:
        team, points = hand_points(st['tricks'], st['hakem'])
        st['scores'][team] += points
        st['round_log'].append({'round': st['round'], 'hakem': st['hakem'], 'trump': st['trump'],
                                'tricks': list(st['tricks']), 'winner': team, 'points': points,
                                'scores': list(st['scores'])})
        st['phase'] = 'hand_end'
        if st['scores'][team] >= TARGET:
            st.update(phase='finished', finished=True, winner=team)


def play_card(state, seat, card):
    st = copy.deepcopy(state)
    _play(st, seat, card)
    return st


def continue_game(state, rng=None):
    if state['finished'] or state['phase'] not in ('trick_end', 'hand_end'):
        raise IllegalMove('cannot_continue')
    st = copy.deepcopy(state)
    st['events'] = []
    if st['phase'] == 'trick_end':
        st.update(trick=[], leader=st['last_trick']['winner'], turn=st['last_trick']['winner'], phase='play')
    else:
        if st['round_log'][-1]['winner'] != st['hakem'] % 2:
            st['hakem'] = (st['hakem'] + 1) % 4
        _deal_hand(st, rng or SR)
    return st


def apply_move(state, card):
    st = copy.deepcopy(state)
    st['events'] = []
    _play(st, HUMAN, card)
    return st


# ---- AI: all policies consume only this observation, never the other hands/deck. ----
def observation(state, seat):
    return {'seat': seat, 'hand': list(state['hands'][seat]),
            'counts': [len(h) for h in state['hands']], 'trick': copy.deepcopy(state['trick']),
            'played': [p['card'] for t in state['trick_history'] for p in t['cards']],
            'trump': state['trump'], 'voids': copy.deepcopy(state['voids']),
            'tricks': list(state['tricks'])}


def choose_trump_ai(hand, level='medium', rng=None):
    rng = rng or SR
    if level == 'easy':
        return rng.choice([c[0] for c in hand])
    return max(SUITS, key=lambda s: (sum(5 + (VALUES[c[1:]] - 2) / 3 for c in hand if c[0] == s), s))


def _legal(hand, trick):
    return [c for c in hand if trick and c[0] == trick[0]['card'][0]] or list(hand)


def _cost(card, trump):
    return VALUES[card[1:]] + (14 if card[0] == trump else 0)


def _medium(hand, seat, trick, trump, played):
    legal = _legal(hand, trick)
    low = min(legal, key=lambda c: (_cost(c, trump), c))
    if not trick:
        unseen = set(ALL_CARDS) - set(played) - set(hand)
        masters = [c for c in legal if not any(x[0] == c[0] and VALUES[x[1:]] > VALUES[c[1:]] for x in unseen)]
        return min(masters, key=lambda c: (_cost(c, trump), c)) if masters else low
    winner = trick_winner(trick, trump)
    if winner % 2 == seat % 2:
        return low
    winning = [c for c in legal if trick_winner(trick + [{'seat': seat, 'card': c}], trump) == seat]
    return min(winning, key=lambda c: (_cost(c, trump), c)) if winning else low


def _sample_hands(view, rng):
    """Random hidden deal consistent with counts and publicly demonstrated void suits.

    Bipartite matching assigns unknown cards to seat slots; it never consults actual
    hidden hands, and never relaxes the void constraints when sampling is difficult.
    """
    known = set(view['hand']) | set(view['played']) | {p['card'] for p in view['trick']}
    unknown = [c for c in ALL_CARDS if c not in known]
    slots = [p for p in range(4) if p != view['seat'] for _ in range(view['counts'][p])]
    rng.shuffle(unknown)
    rng.shuffle(slots)
    assigned = {}
    def match(card, seen):
        choices = [i for i, p in enumerate(slots) if card[0] not in view['voids'][p]]
        rng.shuffle(choices)
        for i in choices:
            if i in seen:
                continue
            seen.add(i)
            if i not in assigned or match(assigned[i], seen):
                assigned[i] = card
                return True
        return False
    if len(unknown) != len(slots) or any(not match(c, set()) for c in unknown):
        raise RuntimeError('inconsistent public card information')
    hands = [[], [], [], []]
    hands[view['seat']] = list(view['hand'])
    for i, c in assigned.items():
        hands[slots[i]].append(c)
    return hands


def choose_card(state, seat, level=None, rng=None):
    rng = rng or SR
    legal = legal_cards(state, seat)
    if not legal:
        raise IllegalMove('no_legal_card')
    level = level or state['level']
    view = observation(state, seat)
    if level == 'easy':
        return rng.choice(legal)
    if level == 'medium' or len(legal) == 1:
        return _medium(view['hand'], seat, view['trick'], view['trump'], view['played'])
    # One-trick Monte Carlo lookahead over legal hidden allocations. The sampled
    # opponents and partner use the medium policy; public voids constrain deals.
    samples = [_sample_hands(view, rng) for _ in range(32)]
    def value(card):
        wins = 0
        for hands in samples:
            trick = list(view['trick']) + [{'seat': seat, 'card': card}]
            p = (seat + 1) % 4
            while len(trick) < 4:
                chosen = _medium(hands[p], p, trick, view['trump'], view['played'])
                trick.append({'seat': p, 'card': chosen})
                p = (p + 1) % 4
            wins += trick_winner(trick, view['trump']) % 2 == seat % 2
        return wins / len(samples) * 100 - _cost(card, view['trump']) * .35
    return max(legal, key=lambda c: (value(c), -VALUES[c[1:]], c))


def play_ai_turns(state, rng=None):
    st = copy.deepcopy(state)
    rng = rng or SR
    for _ in range(5):
        if st['finished'] or st['phase'] in ('trick_end', 'hand_end') or st['turn'] == HUMAN:
            return st
        if st['phase'] == 'choose_trump':
            p = st['hakem']
            st = choose_trump(st, p, choose_trump_ai(st['hands'][p], st['level'], rng))
        else:
            p = st['turn']
            _play(st, p, choose_card(st, p, rng=rng))
    raise RuntimeError('AI did not yield to human or trick boundary')


def public_view(state):
    keys = ('level', 'round', 'hakem', 'dealer', 'turn', 'leader', 'phase', 'trump', 'tricks',
            'scores', 'target_score', 'finished', 'winner', 'draw', 'moves_count', 'identities',
            'selection', 'round_log', 'trick', 'last_trick', 'trick_history', 'events')
    view = {key: copy.deepcopy(state[key]) for key in keys}
    view.update(hand=list(state['hands'][HUMAN]), hand_counts=[len(h) for h in state['hands']],
                legal_cards=legal_cards(state, HUMAN), resigned=state.get('resigned', False),
                can_choose_trump=not state['finished'] and state['phase'] == 'choose_trump' and state['hakem'] == HUMAN,
                can_continue=not state['finished'] and state['phase'] in ('trick_end', 'hand_end'))
    return view


def finish_info(state):
    if not state['finished']:
        raise ValueError('game not finished')
    return ('win' if state['winner'] == 0 else 'loss', f"{state['scores'][0]}-{state['scores'][1]}",
            {'level': state['level'], 'scores': list(state['scores']), 'rounds': state['round'],
             'moves': state['moves_count'], 'rules': 'standard-four-player-v1'})
