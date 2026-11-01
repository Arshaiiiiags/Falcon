"""Groups: membership, chat, seating (partners / rivals), and complete human-vs-human Hokm games."""
import random
import unittest
from unittest.mock import patch
import hokm_engine as h
from test_app import Client, appmod, reset_rate_limits


def make_group(n=2):
    """n registered clients; the first creates a group and the rest join by code."""
    cs = [Client() for _ in range(n)]
    for c in cs:
        c.name, code, _ = c.register()
        assert code == 200
    code, out = cs[0].req('POST', '/api/parties', {'name': 'Friday night'})
    assert code == 201, out
    pid, join = out['party']['id'], out['party']['code']
    for c in cs[1:]:
        assert c.req('POST', '/api/parties/join', {'code': join})[0] == 200
    return cs, pid, join


def poll(c, pid, after=0):
    code, j = c.req('GET', f'/api/parties/{pid}?after={after}')
    assert code == 200, j
    return j


def game(c, pid):
    return c.req('GET', f'/api/parties/{pid}/game')


def sit(c, pid, seat):
    return c.req('POST', f'/api/parties/{pid}/room/seat', {'seat': seat})


class Groups(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()

    def test_create_join_list_and_privacy(self):
        cs, pid, code = make_group(2)
        outsider = Client(); outsider.register()
        self.assertEqual(outsider.req('GET', f'/api/parties/{pid}')[0], 404)      # not a member
        self.assertEqual(outsider.req('POST', f'/api/parties/{pid}/messages', {'text': 'hi'})[0], 404)
        self.assertEqual(outsider.req('POST', '/api/parties/join', {'code': 'ZZZZZZ'})[0], 404)
        self.assertEqual(outsider.req('POST', '/api/parties/join', {'code': code.lower()})[0], 200)  # case-insensitive
        self.assertEqual(outsider.req('POST', '/api/parties/join', {'code': code})[0], 200)          # idempotent
        j = poll(cs[0], pid)
        self.assertEqual([m['username'] for m in j['members']], [cs[0].name, cs[1].name, outsider.req('GET', '/api/me')[1]['user']['username']])
        self.assertTrue(j['party']['is_owner'])
        self.assertFalse(poll(cs[1], pid)['party']['is_owner'])
        self.assertEqual(len(cs[1].req('GET', '/api/parties')[1]['parties']), 1)
        self.assertEqual(Client().req('GET', '/api/parties')[0], 401)

    def test_group_is_capped_and_names_validated(self):
        cs, pid, code = make_group(2)
        self.assertEqual(cs[0].req('POST', '/api/parties', {'name': '   '})[0], 400)
        for _ in range(appmod.party.MAX_MEMBERS - 2):
            c = Client(); c.register()
            self.assertEqual(c.req('POST', '/api/parties/join', {'code': code})[0], 200)
        late = Client(); late.register()
        self.assertEqual(late.req('POST', '/api/parties/join', {'code': code}), (409, {'error': 'party_full'}))

    def test_chat_ordering_sanitising_and_rate_limit(self):
        cs, pid, _ = make_group(2)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/messages', {'text': 'سلام\u202e  <b>hi</b>\n\n there'})[0], 201)
        self.assertEqual(cs[1].req('POST', f'/api/parties/{pid}/messages', {'text': 'hello'})[0], 201)
        msgs = [m for m in poll(cs[1], pid)['messages'] if m['kind'] == 'text']
        self.assertEqual([m['body'] for m in msgs], ['سلام <b>hi</b> there', 'hello'])   # bidi override and newlines removed
        self.assertEqual(msgs[0]['username'], cs[0].name)
        last = msgs[-1]['id']
        self.assertEqual(poll(cs[0], pid, last)['messages'], [])
        cs[1].req('POST', f'/api/parties/{pid}/messages', {'text': 'again'})
        self.assertEqual([m['body'] for m in poll(cs[0], pid, last)['messages']], ['again'])
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/messages', {'text': ''})[0], 400)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/messages', {'text': 'x' * 900})[0], 201)
        self.assertEqual(len([m for m in poll(cs[0], pid)['messages'] if m['body'] == 'x' * 500]), 1)   # truncated
        codes = [cs[0].req('POST', f'/api/parties/{pid}/messages', {'text': f'spam {i}'})[0] for i in range(10)]
        self.assertIn(429, codes)

    def test_leave_transfers_ownership_and_empty_group_is_deleted(self):
        cs, pid, code = make_group(2)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/leave')[0], 200)
        j = poll(cs[1], pid)
        self.assertTrue(j['party']['is_owner'])
        self.assertEqual(j['messages'][-1]['body'], 'left')
        self.assertEqual(cs[0].req('GET', f'/api/parties/{pid}')[0], 404)
        self.assertEqual(cs[1].req('POST', f'/api/parties/{pid}/leave')[0], 200)
        with appmod.db.session_scope(write=False) as s:
            self.assertEqual(s.scalar('SELECT COUNT(*) FROM parties WHERE id=?', (pid,)), 0)
            self.assertEqual(s.scalar('SELECT COUNT(*) FROM party_messages WHERE party_id=?', (pid,)), 0)

    def test_only_owner_can_kick_and_start(self):
        cs, pid, _ = make_group(3)
        uid1 = next(m['user_id'] for m in poll(cs[0], pid)['members'] if m['username'] == cs[1].name)
        self.assertEqual(cs[1].req('POST', f'/api/parties/{pid}/kick', {'user_id': uid1})[0], 403)
        self.assertEqual(cs[1].req('POST', f'/api/parties/{pid}/room/start')[0], 403)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/kick', {'user_id': uid1})[0], 200)
        self.assertEqual(cs[1].req('GET', f'/api/parties/{pid}')[0], 404)


class Table(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()

    def test_seats_partners_rivals_and_start_rules(self):
        cs, pid, _ = make_group(3)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/start'), (409, {'error': 'no_players'}))
        self.assertEqual(sit(cs[0], pid, 0)[0], 200)
        self.assertEqual(sit(cs[1], pid, 0), (409, {'error': 'seat_taken'}))
        self.assertEqual(sit(cs[1], pid, 4)[0], 400)
        self.assertEqual(sit(cs[1], pid, 2)[0], 200)             # partner of seat 0
        self.assertEqual(sit(cs[2], pid, 1)[0], 200)             # rival
        self.assertEqual(sit(cs[1], pid, 3)[0], 200)             # moving frees the old seat
        self.assertEqual(sit(cs[2], pid, 2)[0], 200)
        seats = poll(cs[0], pid)['room']['seats']
        self.assertEqual([x and x['name'] for x in seats], [cs[0].name, None, cs[2].name, cs[1].name])
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/settings', {'level': 'nope'})[0], 400)
        self.assertEqual(cs[1].req('POST', f'/api/parties/{pid}/room/settings', {'level': 'hard'})[0], 403)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/settings', {'level': 'easy'})[0], 200)
        self.assertEqual(game(cs[0], pid)[0], 409)                # no game yet
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/start')[0], 201)
        self.assertEqual(sit(cs[0], pid, 1), (409, {'error': 'invalid_state'}))   # cannot reseat mid-game
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/start')[0], 409)

    def test_every_player_sees_only_their_own_hand_and_is_seat_zero(self):
        cs, pid, _ = make_group(4)
        for i, c in enumerate(cs):
            sit(c, pid, i)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/start')[0], 201)
        views = [game(c, pid)[1] for c in cs]
        hakem_views = [v for v in views if v['state']['can_choose_trump']]
        self.assertEqual(len(hakem_views), 1)
        for i, v in enumerate(views):
            st = v['state']
            self.assertEqual(v['my_seat'], i)
            self.assertEqual(st['names'][0], cs[i].name)                         # viewer is always seat 0
            self.assertEqual(st['names'][2], cs[(i + 2) % 4].name)               # partner opposite
            self.assertEqual(st['kinds'], ['human'] * 4)
            self.assertNotIn('hands', st); self.assertNotIn('deck', st)
            self.assertEqual(len(st['hand']), 5 if st['can_choose_trump'] else 0)
            self.assertEqual(sum(st['hand_counts']), 5)
            self.assertEqual(st['hakem'], 0 if st['can_choose_trump'] else st['hakem'])
        # Wrong player cannot choose trump; the Hakem can.
        waiting = next(i for i, v in enumerate(views) if not v['state']['can_choose_trump'])
        hakem = next(i for i, v in enumerate(views) if v['state']['can_choose_trump'])
        self.assertEqual(cs[waiting].req('POST', f'/api/parties/{pid}/game/trump', {'suit': 'S', 'version': views[waiting]['version']}),
                         (409, {'error': 'not_your_turn'}))
        self.assertEqual(cs[hakem].req('POST', f'/api/parties/{pid}/game/trump', {'suit': 'S', 'version': views[hakem]['version']})[0], 200)
        after = [game(c, pid)[1]['state'] for c in cs]
        self.assertTrue(all(len(s['hand']) == 13 and s['trump'] == 'S' for s in after))
        # Everyone's hand is different and none is a hidden-hand leak of another view.
        self.assertEqual(len({tuple(sorted(s['hand'])) for s in after}), 4)
        self.assertEqual(sum(1 for s in after if s['legal_cards']), 1)           # exactly the player on turn

    def test_stale_version_and_wrong_turn_are_rejected(self):
        cs, pid, _ = make_group(2)
        sit(cs[0], pid, 0); sit(cs[1], pid, 1)
        with patch.object(h, '_draw_hakem', return_value=(0, [{'seat': 0, 'card': 'SA'}])):   # a human is Hakem
            cs[0].req('POST', f'/api/parties/{pid}/room/start')
        v = [game(c, pid)[1] for c in cs]
        h_i = next(i for i in range(2) if v[i]['state']['can_choose_trump'])
        self.assertEqual(cs[h_i].req('POST', f'/api/parties/{pid}/game/trump', {'suit': 'H', 'version': v[h_i]['version'] + 5}),
                         (409, {'error': 'state_conflict'}))
        self.assertEqual(cs[h_i].req('POST', f'/api/parties/{pid}/game/trump', {'suit': 'X', 'version': v[h_i]['version']})[0], 400)
        self.assertEqual(cs[h_i].req('POST', f'/api/parties/{pid}/game/move', {'card': 'SA', 'version': v[h_i]['version']})[0], 409)
        self.assertEqual(cs[h_i].req('POST', f'/api/parties/{pid}/game/trump', {'suit': 'H', 'version': v[h_i]['version']})[0], 200)
        # replaying the same (now stale) request is refused rather than applied twice
        self.assertEqual(cs[h_i].req('POST', f'/api/parties/{pid}/game/trump', {'suit': 'H', 'version': v[h_i]['version']})[0], 409)

    def drive(self, cs, pid, limit=900):
        """Let the humans play (random legal cards) until the game ends."""
        rng = random.Random(7)
        for _ in range(limit):
            views = [game(c, pid)[1] for c in cs]
            if views[0]['match_status'] == 'completed':
                return views
            for i, v in enumerate(views):
                st, base = v['state'], f'/api/parties/{pid}/game/'
                if st['can_choose_trump']:
                    code, _ = cs[i].req('POST', base + 'trump', {'suit': rng.choice('CDHS'), 'version': v['version']}); break
                if st['phase'] == 'play' and st['turn'] == 0:
                    code, _ = cs[i].req('POST', base + 'move', {'card': rng.choice(st['legal_cards']), 'version': v['version']}); break
                if st['can_continue'] and i == 0:
                    code, _ = cs[i].req('POST', base + 'continue', {'version': v['version']}); break
            else:
                self.fail('table is stuck: ' + str([v['state']['phase'] for v in views]))
            self.assertEqual(code, 200)
        self.fail('game did not finish')

    def test_two_humans_as_rivals_and_four_as_two_teams_finish_a_game(self):
        for humans in ([0, 1], [0, 2, 1, 3]):
            with self.subTest(humans=humans):
                cs, pid, _ = make_group(len(humans))
                for c, seat in zip(cs, humans):
                    sit(c, pid, seat)
                cs[0].req('POST', f'/api/parties/{pid}/room/settings', {'level': 'easy'})
                coins = [c.req('GET', '/api/me')[1]['user']['coins'] for c in cs]
                self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/start')[0], 201)
                views = self.drive(cs, pid)
                scores = views[0]['state']['scores']
                self.assertEqual(max(scores), 7)
                # Each player's team 0 is their own team: the views agree once teams are re-mapped.
                for v, seat in zip(views, humans):
                    mine = views[0]['state']['scores'] if seat % 2 == humans[0] % 2 else views[0]['state']['scores'][::-1]
                    self.assertEqual(v['state']['scores'], mine)
                    self.assertEqual(v['state']['winner'] == 0, mine[0] > mine[1])
                self.assertEqual(poll(cs[0], pid)['room']['status'], 'finished')
                self.assertEqual(poll(cs[1], pid)['messages'][-1]['body'], 'game_over')
                self.assertEqual([c.req('GET', '/api/me')[1]['user']['coins'] for c in cs], coins)   # group games are free
                with appmod.db.session_scope(write=False) as s:        # and never touch AI rankings/history
                    self.assertEqual(s.scalar('SELECT COUNT(*) FROM matches'), s.scalar('SELECT COUNT(*) FROM matches'))
                # Owner can go again with the same seats.
                self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/reset')[0], 200)
                self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/start')[0], 201)

    def test_leaving_a_running_game_hands_the_seat_to_ai(self):
        cs, pid, _ = make_group(2)
        sit(cs[0], pid, 0); sit(cs[1], pid, 2)
        cs[0].req('POST', f'/api/parties/{pid}/room/start')
        self.assertEqual(sit(cs[1], pid, None)[0], 200)                       # stand up mid-game
        self.assertEqual(game(cs[1], pid)[0], 409)
        v = game(cs[0], pid)[1]['state']
        self.assertEqual(v['kinds'], ['human', 'ai', 'ai', 'ai'])
        # The remaining human can still finish the game with AI for everyone else.
        self.drive([cs[0]], pid)
        # If the last human leaves, the table closes back to an empty lobby.
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/reset')[0], 200)
        sit(cs[0], pid, 1); cs[0].req('POST', f'/api/parties/{pid}/room/start')
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/leave')[0], 200)
        self.assertEqual(poll(cs[1], pid)['room']['status'], 'lobby')
        self.assertEqual(poll(cs[1], pid)['room']['seats'], [None] * 4)

    def test_kicking_a_seated_player_gives_their_seat_to_ai(self):
        cs, pid, _ = make_group(3)
        sit(cs[0], pid, 0); sit(cs[1], pid, 1); sit(cs[2], pid, 2)
        cs[0].req('POST', f'/api/parties/{pid}/room/start')
        uid = next(m['user_id'] for m in poll(cs[0], pid)['members'] if m['username'] == cs[1].name)
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/kick', {'user_id': uid})[0], 200)
        self.assertEqual(game(cs[0], pid)[1]['state']['kinds'], ['human', 'ai', 'human', 'ai'])
        self.assertEqual(game(cs[1], pid)[0], 404)


class EngineViews(unittest.TestCase):
    def test_rotation_preserves_the_game_for_every_seat(self):
        st = h.play_ai_turns(h.new_party_game('easy', [0, 1, 2, 3], random.Random(3)))
        st = h.choose_trump(st, st['hakem'], 'H')
        st['scores'] = [3, 5]; st['tricks'] = [2, 4]
        for seat in range(4):
            v = h.public_view_for(st, seat, ['a', 'b', 'c', 'd'])
            self.assertEqual(v['names'][0], 'abcd'[seat])
            self.assertEqual(v['hand'], st['hands'][seat])
            self.assertEqual(v['hakem'], (st['hakem'] - seat) % 4)
            self.assertEqual(v['scores'], [3, 5] if seat % 2 == 0 else [5, 3])
            self.assertEqual(v['tricks'], [2, 4] if seat % 2 == 0 else [4, 2])
            self.assertEqual(v['hand_counts'][0], len(st['hands'][seat]))
            self.assertNotIn('hands', v)

    def test_solo_game_is_unchanged(self):
        st = h.new_game('easy', random.Random(1))
        self.assertNotIn('humans', st)
        self.assertEqual(h.play_ai_turns(st)['turn'], 0)
        self.assertNotIn('party', h.public_view(st))


if __name__ == '__main__':
    unittest.main()
