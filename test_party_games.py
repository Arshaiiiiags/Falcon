"""Groups: human-vs-human Pasur and backgammon tables (and switching the table's game)."""
import copy
import json
import random
import unittest

import backgammon_engine as bg
import pasur_engine as ps
from test_app import appmod, reset_rate_limits
from test_party import game, make_group, poll, sit

SETTINGS = '/api/parties/{}/room/settings'


def start(owner, pid):
    return owner.req('POST', f'/api/parties/{pid}/room/start')


def act(c, pid, kind, data, version):
    return c.req('POST', f'/api/parties/{pid}/game/{kind}', {**data, 'version': version})


def pick_pasur(rng, st):
    return rng.choice(st['legal_actions'])


class PasurViews(unittest.TestCase):
    def test_each_seat_sees_itself_as_seat_zero_and_never_the_other_hand_or_deck(self):
        rng = random.Random(3)
        st = ps.new_party_game('easy', [0, 1], rng=rng)
        for _ in range(60):
            if st['finished']:
                break
            v0, v1 = ps.public_view_for(st, 0, ['A', 'B']), ps.public_view_for(st, 1, ['A', 'B'])
            self.assertEqual(v0['hand'], st['hands'][0])
            self.assertEqual(v1['hand'], st['hands'][1])
            self.assertEqual(v0['opponent_hand_count'], len(st['hands'][1]))
            self.assertEqual(v1['opponent_hand_count'], len(st['hands'][0]))
            self.assertEqual((v0['names'], v1['names']), (['A', 'B'], ['B', 'A']))
            self.assertEqual(v0['scores'], v1['scores'][::-1])
            self.assertNotIn('deck', v0)
            self.assertNotIn('hands', v1)
            turn_view = v0 if st['turn'] == 0 else v1
            other_view = v1 if st['turn'] == 0 else v0
            self.assertEqual(turn_view['turn'], 0)
            self.assertEqual(other_view['turn'], 1)
            self.assertTrue(turn_view['legal_actions'])
            self.assertEqual(other_view['legal_actions'], [])
            a = rng.choice(turn_view['legal_actions'])
            st = ps.apply_party_move(st, st['turn'], a['card'], a['capture'], rng)

    def test_ai_fills_an_empty_seat_even_when_it_is_seat_zero(self):
        rng = random.Random(5)
        st = ps.new_party_game('medium', [1], rng=rng)          # the person sits in seat 1
        st = ps.play_ai_for(st, [0], rng)
        self.assertEqual(st['turn'], 1)                         # AI (seat 0) led round 1 and has played
        self.assertEqual(len(st['hands'][0]), 3)
        with self.assertRaises(ValueError):
            ps.new_party_game('medium', [])


class BackgammonViews(unittest.TestCase):
    def play_out(self, rng, cube):
        st = bg.new_party_game('easy', [0, 1], cube=cube, rng=rng)
        for _ in range(4000):
            if st['winner'] is not None:
                return st
            seat = st['turn']
            pend = st['cube']['pending']
            if pend:
                seat = 1 - pend['by']
            real = bg.public_view_for(st, 0)
            view = bg.public_view_for(st, seat)
            # the mirrored board describes the same position from the other side
            self.assertEqual(view['points'] if seat == 0 else [-x for x in view['points'][::-1]], real['points'])
            if view['must_respond']:
                st = bg.respond_double(st, rng.random() < 0.7)
            elif view['can_roll']:
                st = bg.offer_double(st, seat) if view['can_double'] and rng.random() < 0.25 else bg.roll_dice(st, rng)
            else:
                self.assertTrue(view['legal_moves'])
                m = rng.choice(view['legal_moves'])
                src, dst = bg.to_seat_move(seat, m['src'], m['dst'])
                st = bg.apply_move(st, src, dst, m['die'], rng)
        self.fail('game did not finish')

    def test_mirrored_views_drive_a_complete_game(self):
        for seed in (1, 2):
            for cube in (False, True):
                with self.subTest(seed=seed, cube=cube):
                    st = self.play_out(random.Random(seed), cube)
                    self.assertEqual(st['off'][st['winner']], 15 if st['win_type'] != 'cube_drop' else st['off'][st['winner']])
                    v0, v1 = bg.public_view_for(st, 0), bg.public_view_for(st, 1)
                    self.assertEqual(v0['winner'], st['winner'])
                    self.assertEqual(v1['winner'], 1 - st['winner'])
                    self.assertEqual(v0['legal_moves'] + v1['legal_moves'], [])

    def test_ai_plays_an_empty_seat_including_cube_decisions(self):
        rng = random.Random(7)
        for seat_ai in (0, 1):
            st = bg.new_party_game('hard', [1 - seat_ai], cube=True, rng=rng)
            st = bg.play_ai_for(st, [seat_ai], rng)
            self.assertIn(st['turn'], (1 - seat_ai,))
            self.assertIsNone(st['winner'])

    def test_old_single_player_cube_helpers_still_behave(self):
        st = bg.new_game('hard', cube=True)
        self.assertEqual(bg.ai_should_double(st), bg.ai_should_double_for(st, bg.AI))
        self.assertEqual(bg.ai_takes_double(st), bg.ai_takes_double_for(st, bg.AI))


class PartyGames(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()

    def test_owner_chooses_the_game_and_seats_follow(self):
        cs, pid, _ = make_group(3)
        self.assertEqual(poll(cs[0], pid)['room']['game'], 'hokm')
        self.assertEqual(cs[0].req('POST', SETTINGS.format(pid), {})[0], 400)
        self.assertEqual(cs[0].req('POST', SETTINGS.format(pid), {'game': 'chess'})[0], 400)
        self.assertEqual(cs[0].req('POST', SETTINGS.format(pid), {'cube': 'yes'})[0], 400)
        self.assertEqual(cs[1].req('POST', SETTINGS.format(pid), {'game': 'pasur'})[0], 403)
        for i, c in enumerate(cs):
            sit(c, pid, i)                                       # seats 0,1,2 of the four-seat Hokm table
        self.assertEqual(cs[0].req('POST', SETTINGS.format(pid), {'game': 'pasur'})[0], 200)
        room = poll(cs[0], pid)['room']
        self.assertEqual(room['game'], 'pasur')
        self.assertEqual([x and x['name'] for x in room['seats']], [cs[0].name, cs[1].name])   # third person stands up
        self.assertEqual(sit(cs[2], pid, 2)[0], 400)             # only two seats now
        self.assertEqual(sit(cs[2], pid, 1), (409, {'error': 'seat_taken'}))
        self.assertEqual(cs[0].req('POST', SETTINGS.format(pid), {'game': 'backgammon', 'cube': True})[0], 200)
        room = poll(cs[0], pid)['room']
        self.assertEqual((room['game'], room['options']), ('backgammon', {'cube': True}))
        self.assertEqual(cs[0].req('POST', SETTINGS.format(pid), {'game': 'hokm'})[0], 200)
        self.assertEqual(len(poll(cs[0], pid)['room']['seats']), 4)
        self.assertEqual(start(cs[0], pid)[0], 201)
        self.assertEqual(cs[0].req('POST', SETTINGS.format(pid), {'game': 'pasur'}), (409, {'error': 'invalid_state'}))
        self.assertEqual(act(cs[0], pid, 'roll', {}, 0)[0], 400)  # not a Hokm action

    def test_two_people_play_a_whole_pasur_game(self):
        rng = random.Random(11)
        cs, pid, _ = make_group(2)
        cs[0].req('POST', SETTINGS.format(pid), {'game': 'pasur', 'level': 'easy'})
        sit(cs[0], pid, 0); sit(cs[1], pid, 1)
        self.assertEqual(start(cs[0], pid)[0], 201)
        self.assertEqual(poll(cs[1], pid)['messages'][-1]['body'], 'game_start_pasur')
        for _ in range(900):
            views = [game(c, pid)[1] for c in cs]
            if views[0]['match_status'] == 'completed':
                break
            mover = next(i for i, v in enumerate(views) if v['state']['turn'] == 0)
            other = 1 - mover
            self.assertEqual(views[other]['state']['legal_actions'], [])
            # the waiting player is refused with not_your_turn, never silently accepted
            a0 = (views[other]['state']['hand'] or ['C2'])[0]   # a player may have just played their last card
            self.assertEqual(act(cs[other], pid, 'move', {'card': a0, 'capture': []}, views[other]['version'])[1],
                             {'error': 'not_your_turn'})
            a = pick_pasur(rng, views[mover]['state'])
            code, out = act(cs[mover], pid, 'move', a, views[mover]['version'])
            self.assertEqual(code, 200, out)
            self.assertEqual(out['state']['names'][0], cs[mover].name)
        else:
            self.fail('game did not finish')
        v = [game(c, pid)[1]['state'] for c in cs]
        self.assertTrue(v[0]['finished'] and v[1]['finished'])
        self.assertEqual(v[0]['scores'], v[1]['scores'][::-1])
        if not v[0]['draw']:
            self.assertEqual((v[0]['winner'], v[1]['winner']), (0, 1) if v[0]['scores'][0] > v[0]['scores'][1] else (1, 0))
        self.assertEqual(poll(cs[0], pid)['room']['status'], 'finished')
        self.assertEqual(cs[0].req('POST', f'/api/parties/{pid}/room/reset')[0], 200)

    def test_illegal_pasur_moves_and_stale_versions_are_rejected(self):
        cs, pid, _ = make_group(2)
        cs[0].req('POST', SETTINGS.format(pid), {'game': 'pasur'})
        sit(cs[0], pid, 0); sit(cs[1], pid, 1)
        start(cs[0], pid)
        views = [game(c, pid)[1] for c in cs]
        m = next(i for i, v in enumerate(views) if v['state']['turn'] == 0)
        st, ver = views[m]['state'], views[m]['version']
        self.assertEqual(act(cs[m], pid, 'move', {'card': 'ZZ', 'capture': []}, ver)[1], {'error': 'illegal_move'})
        self.assertEqual(act(cs[m], pid, 'move', {'card': st['hand'][0], 'capture': ['nope']}, ver)[1], {'error': 'illegal_move'})
        self.assertEqual(act(cs[m], pid, 'move', {'card': st['hand'][0]}, 'x')[0], 400)
        a = st['legal_actions'][0]
        self.assertEqual(act(cs[m], pid, 'move', a, ver)[0], 200)
        self.assertEqual(act(cs[m], pid, 'move', a, ver)[1], {'error': 'state_conflict'})

    def test_two_people_play_a_whole_backgammon_game_with_the_cube(self):
        rng = random.Random(21)
        cs, pid, _ = make_group(2)
        cs[0].req('POST', SETTINGS.format(pid), {'game': 'backgammon', 'cube': True, 'level': 'easy'})
        sit(cs[0], pid, 0); sit(cs[1], pid, 1)
        self.assertEqual(start(cs[0], pid)[0], 201)
        self.assertEqual(poll(cs[0], pid)['room']['options'], {'cube': True})
        for _ in range(3000):
            views = [game(c, pid)[1] for c in cs]
            if views[0]['match_status'] == 'completed':
                break
            for i, v in enumerate(views):
                st = v['state']
                if st['must_respond']:
                    code, _ = act(cs[i], pid, 'respond', {'accept': rng.random() < 0.7}, v['version'])
                elif st['can_roll']:
                    kind = 'double' if st['can_double'] and rng.random() < 0.25 else 'roll'
                    code, _ = act(cs[i], pid, kind, {}, v['version'])
                elif st['legal_moves']:
                    m = rng.choice(st['legal_moves'])
                    code, out = act(cs[i], pid, 'move', m, v['version'])
                    self.assertEqual(code, 200, out)
                else:
                    continue
                self.assertEqual(code, 200)
                break
            else:
                self.fail('nobody can act')
        else:
            self.fail('game did not finish')
        v = [game(c, pid)[1]['state'] for c in cs]
        self.assertIsNotNone(v[0]['winner'])
        self.assertEqual(v[0]['winner'], 1 - v[1]['winner'])
        self.assertEqual(poll(cs[1], pid)['room']['status'], 'finished')

    def test_backgammon_turn_rules_and_mirrored_moves(self):
        cs, pid, _ = make_group(2)
        cs[0].req('POST', SETTINGS.format(pid), {'game': 'backgammon', 'cube': True})
        sit(cs[0], pid, 0); sit(cs[1], pid, 1)
        start(cs[0], pid)
        for _ in range(60):
            views = [game(c, pid)[1] for c in cs]
            roller = next((i for i, v in enumerate(views) if v['state']['can_roll']), None)
            if roller is not None:
                other = 1 - roller
                self.assertEqual(act(cs[other], pid, 'roll', {}, views[other]['version'])[1], {'error': 'not_your_turn'})
                self.assertEqual(act(cs[other], pid, 'double', {}, views[other]['version'])[1], {'error': 'not_your_turn'})
                self.assertEqual(act(cs[roller], pid, 'respond', {'accept': True}, views[roller]['version'])[1], {'error': 'not_your_turn'})
                break
            m = next(i for i, v in enumerate(views) if v['state']['legal_moves'])
            mv = views[m]['state']['legal_moves'][0]
            self.assertEqual(act(cs[1 - m], pid, 'move', mv, views[1 - m]['version'])[1], {'error': 'not_your_turn'})
            bad = dict(mv, src=(mv['src'] + 1) % 24 if mv['src'] != 'bar' else 0)
            if bad['src'] != mv['src'] and not any(x['src'] == bad['src'] and x['dst'] == bad['dst'] for x in views[m]['state']['legal_moves']):
                self.assertEqual(act(cs[m], pid, 'move', bad, views[m]['version'])[1], {'error': 'illegal_move'})
            self.assertEqual(act(cs[m], pid, 'move', mv, views[m]['version'])[0], 200)
        else:
            self.fail('never reached a roll decision')

    def test_leaving_hands_the_seat_to_the_ai_and_an_empty_table_closes(self):
        for kind in ('pasur', 'backgammon'):
            with self.subTest(game=kind):
                cs, pid, _ = make_group(2)
                cs[0].req('POST', SETTINGS.format(pid), {'game': kind, 'level': 'easy'})
                sit(cs[0], pid, 0); sit(cs[1], pid, 1)
                start(cs[0], pid)
                self.assertEqual(sit(cs[1], pid, None)[0], 200)             # stand up mid-game
                room = poll(cs[0], pid)['room']
                self.assertEqual(room['status'], 'active')
                self.assertEqual(room['seats'][1], None)
                self.assertEqual(game(cs[1], pid)[0], 409)
                # the AI has moved on: the remaining person is always the one on turn (or the game is over)
                st = game(cs[0], pid)[1]['state']
                self.assertTrue(st['turn'] == 0 or st.get('winner') is not None or st.get('finished'))
                self.assertEqual(sit(cs[0], pid, None)[0], 200)             # last person leaves
                room = poll(cs[0], pid)['room']
                self.assertEqual((room['status'], room['seats']), ('lobby', [None, None]))

    def test_a_person_in_seat_one_is_led_by_the_ai_in_seat_zero(self):
        cs, pid, _ = make_group(1)
        cs[0].req('POST', SETTINGS.format(pid), {'game': 'pasur', 'level': 'medium'})
        sit(cs[0], pid, 1)
        self.assertEqual(start(cs[0], pid)[0], 201)
        v = game(cs[0], pid)[1]
        self.assertEqual(v['my_seat'], 1)
        self.assertEqual(v['state']['turn'], 0)                   # my turn, shown as seat 0
        self.assertEqual(v['state']['kinds'], ['human', 'ai'])
        self.assertEqual(v['state']['opponent_hand_count'], 3)    # the AI already played a card
        a = v['state']['legal_actions'][0]
        self.assertEqual(act(cs[0], pid, 'move', a, v['version'])[0], 200)

    def test_spectators_get_summary_only(self):
        cs, pid, _ = make_group(3)
        cs[0].req('POST', SETTINGS.format(pid), {'game': 'backgammon'})
        sit(cs[0], pid, 0); sit(cs[1], pid, 1)
        start(cs[0], pid)
        room = poll(cs[2], pid)['room']
        self.assertEqual((room['game'], room['my_seat']), ('backgammon', None))
        self.assertEqual(room['off'], [0, 0])
        self.assertNotIn('points', json.dumps(room))
        self.assertEqual(game(cs[2], pid)[0], 409)

    def test_existing_hokm_room_rows_default_to_hokm(self):
        cs, pid, _ = make_group(1)
        with appmod.db.session_scope(write=False) as s:
            row = s.one('SELECT game, options_json FROM party_rooms WHERE party_id=?', (pid,))
        self.assertEqual((row['game'], row['options_json']), ('hokm', '{}'))


if __name__ == '__main__':
    unittest.main()
