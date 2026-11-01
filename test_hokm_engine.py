"""Rules, privacy, AI information boundaries, and complete four-seat Hokm matches."""
import copy
import json
import random
import unittest
import hokm_engine as h


def dealt(seed=1, level='medium'):
    st = h.new_game(level, random.Random(seed))
    return h.choose_trump(st, st['hakem'], 'S')


class HokmRules(unittest.TestCase):
    def test_ace_draw_partners_reseated_and_only_hakem_gets_five(self):
        for seed in range(50):
            st = h.new_game(rng=random.Random(seed))
            aces = [p for p in st['selection'] if p['card'].endswith('A')]
            self.assertEqual(len(aces), 2)
            self.assertEqual(aces[0]['seat'], st['hakem'])
            self.assertEqual(aces[1]['seat'], (st['hakem'] + 2) % 4)
            self.assertEqual(len(st['hands'][st['hakem']]), 5)
            self.assertEqual(sum(map(len, st['hands'])), 5)
            self.assertEqual(len(st['deck']), 47)
            self.assertEqual(st['dealer'], (st['hakem'] - 1) % 4)
            self.assertEqual(st['identities'][0], 0)
            self.assertEqual(sorted(st['identities']), list(range(4)))
            self.assertEqual(len(set(st['deck'] + sum(st['hands'], []))), 52)

    def test_five_four_four_packets_and_every_trump(self):
        for suit in h.SUITS:
            st = h.new_game(rng=random.Random(7))
            original = copy.deepcopy(st)
            out = h.choose_trump(st, st['hakem'], suit)
            self.assertEqual(st, original)
            self.assertEqual(list(map(len, out['hands'])), [13]*4)
            self.assertFalse(out['deck'])
            self.assertEqual(set(sum(out['hands'], [])), set(h.ALL_CARDS))
            self.assertEqual(out['hands'][st['hakem']][:5], st['hands'][st['hakem']])
            # The next five cards go to the next seat before any four-card packet.
            self.assertEqual(out['hands'][(st['hakem']+1)%4][:5], list(reversed(st['deck'][-5:])))
            self.assertEqual(out['turn'], st['hakem'])
            self.assertEqual(out['trump'], suit)

    def test_trump_cannot_be_changed_or_chosen_by_another_seat(self):
        st = h.new_game(rng=random.Random(3))
        for seat, suit in [(st['dealer'],'S'),(None,'S'),(True,'S'),(st['hakem'],None),(st['hakem'],{}),(st['hakem'],'X')]:
            with self.assertRaises(h.IllegalMove): h.choose_trump(st,seat,suit)
        out=h.choose_trump(st,st['hakem'],'H')
        with self.assertRaises(h.IllegalMove):h.choose_trump(out,out['hakem'],'S')
        with self.assertRaises(h.IllegalMove):h.apply_move(st,st['hands'][st['hakem']][0])

    def test_rank_trump_and_led_suit_determine_winner(self):
        for trump, cards, expected in [('S',['HA','H2','HK','HQ'],0),('S',['HA','S2','HK','SA'],3),
                                       ('S',['H2','DA','CA','HK'],3),('H',['S2','SA','H2','SK'],2),
                                       ('C',['SJ','SQ','SK','SA'],3)]:
            self.assertEqual(h.trick_winner([{'seat':i,'card':c} for i,c in enumerate(cards)],trump),expected)

    def test_follow_suit_required_but_no_obligation_to_trump(self):
        st=dealt();st.update(turn=0,trick=[{'seat':3,'card':'H2'}]);st['hands'][0]=['HA','S2','C2']
        self.assertEqual(h.legal_cards(st),['HA'])
        for c in ['S2','C2',None,{},[],True,'H3']:
            with self.assertRaises(h.IllegalMove):h.apply_move(st,c)
        st['hands'][0]=['S2','C2']
        self.assertEqual(h.legal_cards(st),['S2','C2'])
        out=h.apply_move(st,'C2')
        self.assertIn('H',out['voids'][0])
        self.assertNotIn('H',st['voids'][0])

    def test_turn_order_trick_pause_and_winner_leads(self):
        st=dealt();st.update(turn=0,leader=0,trick=[])
        st['hands']=[['H2'],['HA'],['HK'],['HQ']]
        for seat in range(4):
            self.assertEqual(st['turn'],seat)
            st=h.play_card(st,seat,st['hands'][seat][0])
        self.assertEqual(st['phase'],'trick_end')
        self.assertEqual(len(st['trick']),4)
        self.assertEqual(st['last_trick']['winner'],1)
        self.assertEqual(st['tricks'],[0,1])
        self.assertEqual(h.legal_cards(st,0),[])
        nxt=h.continue_game(st)
        self.assertEqual((nxt['turn'],nxt['leader'],nxt['trick']),(1,1,[]))
        self.assertEqual(len(nxt['trick_history']),1)

    def test_regular_kot_and_hakem_kot_scoring(self):
        for tricks,hakem,result in [([7,3],0,(0,1)),([2,7],2,(1,1)),([7,0],0,(0,2)),
                                    ([7,0],1,(0,3)),([0,7],3,(1,2)),([0,7],0,(1,3))]:
            self.assertEqual(h.hand_points(tricks,hakem),result)
        with self.assertRaises(ValueError):h.hand_points([6,6],0)

    def hand_end(self,hakem,winner=0):
        st=dealt();st.update(hakem=hakem,turn=3,tricks=[6,1],trick=[{'seat':0,'card':'SA'},{'seat':1,'card':'S2'},{'seat':2,'card':'S3'}])
        st['hands'][3]=['S4','C5']
        return h.play_card(st,3,'S4')

    def test_hand_stops_at_seven_without_playing_remaining_cards(self):
        st=self.hand_end(0)
        self.assertEqual(st['phase'],'hand_end');self.assertEqual(st['scores'],[1,0])
        self.assertEqual(st['tricks'],[7,1]);self.assertEqual(st['hands'][3],['C5'])
        self.assertEqual(st['round_log'][0]['points'],1)
        with self.assertRaises(h.IllegalMove):h.play_card(st,3,'C5')

    def test_hakem_retained_or_passes_right_after_loss(self):
        for hakem,expected in [(0,0),(2,2),(1,2),(3,0)]:
            st=self.hand_end(hakem);out=h.continue_game(st,random.Random(4))
            self.assertEqual(out['hakem'],expected)
            self.assertEqual(out['dealer'],(expected-1)%4)
            self.assertEqual(out['round'],2)
            self.assertEqual(out['phase'],'choose_trump')
            self.assertEqual(out['tricks'],[0,0]);self.assertEqual(out['trick_history'],[])
            self.assertEqual(out['selection'],st['selection'])
            self.assertEqual(out['scores'],st['scores'])

    def test_match_finishes_at_seven_and_no_more_actions(self):
        st=dealt();st.update(hakem=0,scores=[6,2],turn=3,tricks=[6,1],trick=[{'seat':0,'card':'SA'},{'seat':1,'card':'S2'},{'seat':2,'card':'S3'}]);st['hands'][3]=['S4']
        st=h.play_card(st,3,'S4')
        self.assertTrue(st['finished']);self.assertEqual(st['winner'],0)
        self.assertEqual(st['scores'],[7,2]);self.assertEqual(st['phase'],'finished')
        self.assertEqual(h.finish_info(st)[:2],('win','7-2'))
        with self.assertRaises(h.IllegalMove):h.continue_game(st)
        with self.assertRaises(h.IllegalMove):h.play_card(st,0,'C2')
        self.assertFalse(h.public_view(st)['can_continue'])

    def test_public_view_never_discloses_ai_hands_or_deck(self):
        for st in [h.new_game(rng=random.Random(2)),dealt()]:
            view=h.public_view(st)
            self.assertNotIn('deck',view);self.assertNotIn('hands',view)
            self.assertNotIn('voids',view)
            self.assertEqual(view['hand'],st['hands'][0])
            self.assertEqual(view['hand_counts'],list(map(len,st['hands'])))
            self.assertEqual(json.loads(json.dumps(st)),st)
            self.assertEqual(view['events'],[] if st['phase']=='choose_trump' else [{'type':'trump','seat':st['hakem'],'suit':'S'}])

    def test_wrong_seat_and_wrong_phase_are_rejected_without_mutation(self):
        st=dealt();saved=copy.deepcopy(st)
        for seat in [None,True,-1,4,(st['turn']+1)%4]:
            with self.assertRaises(h.IllegalMove):h.play_card(st,seat,'SA')
        with self.assertRaises(h.IllegalMove):h.continue_game(st)
        self.assertEqual(st,saved)


class HokmAI(unittest.TestCase):
    def test_medium_saves_high_cards_when_partner_wins(self):
        st=dealt();st.update(turn=3,trick=[{'seat':0,'card':'H2'},{'seat':1,'card':'HA'},{'seat':2,'card':'HK'}]);st['hands'][3]=['H3','HQ']
        self.assertEqual(h.choose_card(st,3,'medium'),'H3')
        st['trick'][1]['card']='H4';st['trick'][2]['card']='H5'
        self.assertEqual(h.choose_card(st,3,'medium'),'HQ')

    def test_hard_choice_does_not_depend_on_actual_hidden_hands(self):
        st=dealt(level='hard');seat=st['turn'];other=copy.deepcopy(st)
        hidden=[p for p in range(4) if p!=seat]
        other['hands'][hidden[0]],other['hands'][hidden[1]]=other['hands'][hidden[1]],other['hands'][hidden[0]]
        other['deck']=['bogus'] # not available to the policy
        for level in h.LEVELS:
            self.assertEqual(h.choose_card(st,seat,level,random.Random(19)),h.choose_card(other,seat,level,random.Random(19)))

    def test_sampling_respects_public_voids_and_counts(self):
        st=dealt();st.update(turn=0,trick=[])
        # A valid deal where one opponent is void of hearts.
        hearts=[c for c in st['hands'][1] if c[0]=='H']
        swaps=[c for c in st['hands'][2] if c[0]!='H'][:len(hearts)]
        for a,b in zip(hearts,swaps):
            st['hands'][1].remove(a);st['hands'][2].remove(b);st['hands'][1].append(b);st['hands'][2].append(a)
        st['voids'][1]=['H']
        view=h.observation(st,0)
        for seed in range(10):
            hands=h._sample_hands(view,random.Random(seed))
            self.assertEqual(list(map(len,hands)),[13]*4)
            self.assertFalse(any(c[0]=='H' for c in hands[1]))
            self.assertEqual(set(sum(hands,[])),set(h.ALL_CARDS))

    def test_ai_yields_at_human_decisions_and_trick_boundaries(self):
        for seed in range(12):
            st=h.play_ai_turns(h.new_game(rng=random.Random(seed)),random.Random(seed))
            self.assertEqual(st['turn'],0)
            self.assertIn(st['phase'],('choose_trump','play'))
            if st['phase']=='choose_trump':self.assertEqual(len(st['hands'][0]),5)

    def test_complete_games_keep_cards_turns_scoring_and_privacy_consistent(self):
        for level,seeds in [('easy',range(8)),('medium',range(8)),('hard',range(2))]:
            for seed in seeds:
                with self.subTest(level=level,seed=seed):
                    rng=random.Random(seed);st=h.new_game(level,rng);steps=0
                    while not st['finished']:
                        self.assertLess(steps,800)
                        # Every card occurs exactly once in the live hand, deck or played tricks.
                        played=[p['card'] for tr in st['trick_history'] for p in tr['cards']]
                        current=[] if st['phase'] in ('trick_end','hand_end') else [p['card'] for p in st['trick']]
                        cards=sum(st['hands'],[])+st['deck']+played+current
                        self.assertEqual(len(cards),52);self.assertEqual(set(cards),set(h.ALL_CARDS))
                        if st['phase']=='choose_trump':st=h.choose_trump(st,st['hakem'],h.choose_trump_ai(st['hands'][st['hakem']],level,rng))
                        elif st['phase']=='play':
                            seat=st['turn'];c=h.choose_card(st,seat,level,rng)
                            self.assertIn(c,h.legal_cards(st,seat));st=h.play_card(st,seat,c)
                        else:st=h.continue_game(st,rng)
                        steps+=1
                    self.assertGreaterEqual(st['scores'][st['winner']],7)
                    self.assertLessEqual(st['round'],13)
                    self.assertEqual(st['scores'],[sum(r['points'] for r in st['round_log'] if r['winner']==team) for team in range(2)])
                    self.assertEqual(h.finish_info(st)[0],'win' if st['winner']==0 else 'loss')


if __name__=='__main__':unittest.main()
