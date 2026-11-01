"""Hokm API, persistence, accounting, privacy, concurrency, and complete matches."""
import copy
import json
import random
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import hokm_engine as h
from test_app import Client,appmod,reset_rate_limits


def human_hakem(level='medium'):
    for seed in range(100):
        st=h.new_game(level,random.Random(seed))
        if st['hakem']==0:return st
    raise AssertionError('no human Hakem seed')


class HokmApi(unittest.TestCase):
    def setUp(self):
        reset_rate_limits();self.c=Client();self.username,code,_=self.c.register();self.assertEqual(code,200)

    def active(self,start=True,level='medium'):
        code,out=self.c.new_match('hokm');self.assertEqual(code,201)
        mid=out['match']['id'];self.assertEqual(self.c.req('POST',f'/api/matches/{mid}/activate')[0],200)
        if not start:return mid
        # Isolated deterministic fixture: always exercise human trump choice.
        st=human_hakem(level)
        with patch.object(appmod.hk,'new_game',return_value=st):
            code,out=self.c.req('POST',f'/api/matches/{mid}/hokm/start',{'level':level})
        self.assertEqual(code,201)
        return mid,out

    def action(self,mid,out,kind,**data):
        return self.c.req('POST',f'/api/matches/{mid}/hokm/{kind}',{'version':out['version'],**data})

    def test_four_seats_charge_once_and_start_idempotency(self):
        mid,out=self.active()
        self.assertEqual(out['state']['hand_counts'],[5,0,0,0])
        self.assertTrue(out['state']['can_choose_trump'])
        self.assertEqual(self.c.req('GET','/api/me')[1]['user']['coins'],95)
        again=self.c.req('POST',f'/api/matches/{mid}/hokm/start',{'level':'hard'})
        self.assertEqual(again,(200,out))
        with appmod.db.session_scope(write=False) as tx:
            self.assertEqual(tx.scalar('SELECT COUNT(*) FROM match_players WHERE match_id=?',(mid,)),4)
            self.assertEqual(tx.scalar("SELECT COUNT(*) FROM coin_transactions WHERE match_id=? AND kind='match_fee'",(mid,)),1)

    def test_trump_deals_remaining_cards_and_ai_stops_at_human(self):
        mid,out=self.active();code,out=self.action(mid,out,'trump',suit='H')
        self.assertEqual(code,200);self.assertEqual(out['state']['hand_counts'],[13]*4)
        self.assertEqual(out['state']['turn'],0);self.assertEqual(out['state']['trump'],'H')
        self.assertNotIn('hands',out['state']);self.assertNotIn('deck',out['state'])
        self.assertEqual(self.action(mid,out,'trump',suit='S')[0],400)

    def test_invalid_inputs_do_not_change_state(self):
        mid,out=self.active();url=f'/api/matches/{mid}/hokm'
        for d in [{},{'version':True,'suit':'S'},{'version':'0','suit':'S'}]:
            self.assertEqual(self.c.req('POST',url+'/trump',d)[0],400)
        for suit in [None,{},[],True,'X','']:
            self.assertEqual(self.action(mid,out,'trump',suit=suit)[0],400)
        self.assertEqual(self.action(mid,out,'move',card=out['state']['hand'][0])[0],400)
        self.assertEqual(self.action(mid,out,'continue')[0],400)
        self.assertEqual(self.c.req('GET',url)[1],out)
        for level in [None,{},[],True,'expert']:
            self.assertEqual(self.c.req('POST',url+'/start',{'level':level})[0],400)

    def test_owner_csrf_and_wrong_game_boundaries(self):
        mid,out=self.active();other=Client();other.register()
        self.assertEqual(other.req('GET',f'/api/matches/{mid}/hokm')[0],404)
        self.assertEqual(other.req('POST',f'/api/matches/{mid}/hokm/trump',{'version':0,'suit':'S'})[0],404)
        self.assertEqual(self.c.req('POST',f'/api/matches/{mid}/hokm/trump',{'version':0,'suit':'S'},csrf=False)[0],403)
        self.assertEqual(self.c.req('GET',f'/api/matches/{mid}/pasur')[0],404)
        anon=Client();self.assertEqual(anon.req('GET',f'/api/matches/{mid}/hokm')[0],401)

    def test_stale_versions_and_duplicate_moves_do_not_play_twice(self):
        mid,out=self.active();code,dealt=self.action(mid,out,'trump',suit='S');self.assertEqual(code,200)
        self.assertEqual(self.action(mid,out,'trump',suit='H')[0],409)
        code,next_state=self.action(mid,dealt,'move',card=dealt['state']['legal_cards'][0]);self.assertEqual(code,200)
        self.assertEqual(len(next_state['state']['trick']),4)
        self.assertEqual(next_state['state']['phase'],'trick_end')
        self.assertEqual(self.action(mid,dealt,'move',card=dealt['state']['legal_cards'][0])[0],409)
        self.assertEqual(self.c.req('GET',f'/api/matches/{mid}/hokm')[1],next_state)

    def test_concurrent_trump_requests_only_commit_one(self):
        mid,out=self.active()
        def submit(suit):
            other=Client();other.c.set_cookie('session',self.c.c.get_cookie('session').value);other.csrf=self.c.csrf
            return other.req('POST',f'/api/matches/{mid}/hokm/trump',{'version':out['version'],'suit':suit})[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes=list(pool.map(submit,['H','S']))
        self.assertEqual(sorted(codes),[200,409])
        saved=self.c.req('GET',f'/api/matches/{mid}/hokm')[1]
        self.assertEqual(saved['version'],1);self.assertEqual(saved['state']['hand_counts'],[13]*4)

    def test_resignation_updates_state_history_stats_and_ranking(self):
        mid,out=self.active();code,out=self.action(mid,out,'trump',suit='S');self.assertEqual(code,200)
        self.assertEqual(self.c.req('POST',f'/api/matches/{mid}/hokm/resign')[0],200)
        saved=self.c.req('GET',f'/api/matches/{mid}/hokm')[1]
        self.assertEqual(saved['match_status'],'completed');self.assertTrue(saved['state']['resigned'])
        self.assertEqual(saved['state']['phase'],'finished');self.assertEqual(saved['state']['winner'],1)
        self.assertEqual(saved['state']['scores'],[0,0])
        self.assertEqual(self.action(mid,saved,'move',card=saved['state']['hand'][0])[0],409)
        self.assertEqual(self.c.req('POST',f'/api/matches/{mid}/hokm/resign')[0],409)
        me=self.c.req('GET','/api/me')[1]['user'];self.assertEqual(me['stats']['hokm']['lost'],1)
        history=self.c.req('GET','/api/matches?game=hokm')[1]['matches'][0]
        self.assertEqual((history['game'],history['result'],history['score']),('hokm','loss','0-0'))
        ranks=self.c.req('GET','/api/leaderboard?game=hokm&level=medium')[1]
        self.assertTrue(any(r['username']==self.username and r['played']==1 for r in ranks['leaderboard']))

    def test_complete_match_saves_once_and_earns_correct_game_achievement(self):
        mid,out=self.active();steps=0
        while out['match_status']=='active':
            self.assertLess(steps,700)
            st=out['state']
            if st['can_choose_trump']:kind,data='trump',{'suit':'S'}
            elif st['can_continue']:kind,data='continue',{}
            else:kind,data='move',{'card':st['legal_cards'][0]}
            code,next_state=self.action(mid,out,kind,**data);self.assertEqual(code,200,next_state)
            out=next_state;steps+=1
        self.assertTrue(out['state']['finished']);self.assertGreaterEqual(max(out['state']['scores']),7)
        self.assertEqual(self.c.req('GET',f'/api/matches/{mid}/hokm')[1],out)
        with appmod.db.session_scope(write=False) as tx:
            self.assertEqual(tx.scalar('SELECT COUNT(*) FROM match_results WHERE match_id=?',(mid,)),1)
        me=self.c.req('GET','/api/me')[1]['user'];self.assertEqual(me['stats']['hokm']['played'],1)
        self.assertEqual(me['stats']['backgammon']['played'],0)
        self.assertEqual(me['coins'],95)
        achievements=self.c.req('GET','/api/achievements')[1]['achievements']
        earned={a['key'] for a in achievements if a['earned']}
        self.assertNotIn('backgammon_win',earned)
        self.assertEqual('hokm_win' in earned,out['state']['winner']==0)

    def test_winning_hokm_earns_hokm_badge_only(self):
        mid,out=self.active()
        st=h.choose_trump(human_hakem(),0,'S')
        st.update(scores=[6,0],tricks=[6,1],turn=0,trick=[{'seat':1,'card':'S2'},{'seat':2,'card':'S3'},{'seat':3,'card':'S4'}])
        st['hands'][0]=['SA']
        with appmod.db.session_scope() as tx:
            tx.execute('UPDATE game_states SET state_json=? WHERE match_id=?',(json.dumps(st),mid))
        code,out=self.action(mid,out,'move',card='SA');self.assertEqual(code,200)
        self.assertEqual(out['match_status'],'completed');self.assertEqual(out['state']['scores'],[7,0])
        earned={a['key'] for a in self.c.req('GET','/api/achievements')[1]['achievements'] if a['earned']}
        self.assertTrue({'hokm_win','first_win'}<=earned);self.assertNotIn('backgammon_win',earned)

    def test_hokm_module_served_but_engine_private(self):
        with self.c.c.get('/hokm.js') as response:self.assertEqual(response.status_code,200)
        self.assertEqual(self.c.req('GET','/hokm_engine.py')[0],404)


if __name__=='__main__':unittest.main()
