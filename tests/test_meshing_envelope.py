import copy
import unittest
from a3d.meshing_envelope import MeshingEnvelope
from a3d.core import StudioError


class MeshingEnvelopeTests(unittest.TestCase):
    def make(self, **kwargs):
        return MeshingEnvelope('coat', {'attempted_insertions':4, 'native_cdt_calls':3,
                                      'sampling_calls':8}, clock=lambda:0., **kwargs)

    def test_controls_and_native_attempts_share_component_budget(self):
        e=self.make()
        e.observe_material_controls('coat', {'a':[{'source':'one','parameter':'1/3'}], 'b':['different']})
        e.reserve('attempted_insertions',2,owner='a')
        with self.assertRaises(StudioError) as caught:e.reserve('attempted_insertions',1,owner='b')
        self.assertEqual(caught.exception.reason,'BUDGET_EXHAUSTED')
        self.assertEqual(e.snapshot()['work']['attempted_insertions'],4)
        self.assertEqual(dict(e.material_controls),{'a':1,'b':1})

    def test_identical_control_replay_is_union_while_work_is_debited(self):
        e=self.make(); controls={'a':[{'parameter':'1/3','source':'sha'}]}
        e.observe_material_controls('coat',controls)
        e.observe_material_controls('coat',copy.deepcopy(controls))
        e.reserve('sampling_calls',1);e.reserve('sampling_calls',1)
        self.assertEqual(e.snapshot()['work']['attempted_insertions'],1)
        self.assertEqual(e.snapshot()['work']['sampling_calls'],2)
        e.observe_material_controls('coat',{'a':[{'parameter':'10000000000000001/30000000000000000','source':'sha'}]})
        self.assertEqual(e.material_controls['a'],2)

    def test_local_limits_and_global_limits_are_both_required(self):
        e=self.make(owner_limits={'native_cdt_calls':2})
        e.reserve('native_cdt_calls',2,owner='a')
        with self.assertRaises(StudioError):e.reserve('native_cdt_calls',1,owner='a')
        e.reserve('native_cdt_calls',1,owner='b')
        with self.assertRaises(StudioError):e.reserve('native_cdt_calls',1,owner='b')
        self.assertEqual(e.snapshot()['work']['native_cdt_calls'],3)

    def test_over_budget_control_set_is_not_partially_inserted(self):
        e=self.make()
        with self.assertRaises(StudioError):e.observe_material_controls('coat',{'a':[1,2,3], 'b':[4,5]})
        self.assertEqual(dict(e.material_controls),{})
        self.assertEqual(e.snapshot()['work']['attempted_insertions'],0)

    def test_snapshots_and_controls_cannot_refund_live_work(self):
        e=self.make();e.observe_material_controls('coat',{'a':['x']})
        snap=e.snapshot();snap['work']['attempted_insertions']=0;snap['owner_work']['a']['attempted_insertions']=0
        with self.assertRaises(TypeError):e.material_controls['a']=0
        self.assertEqual(e.snapshot()['work']['attempted_insertions'],1)

    def test_deadline_at_boundary_refuses_without_refund(self):
        now=[0.];e=MeshingEnvelope('coat',{'attempted_insertions':4},max_seconds=10.,clock=lambda:now[0])
        e.reserve('attempted_insertions',2,owner='a');now[0]=10.
        with self.assertRaises(StudioError) as caught:e.reserve('attempted_insertions',1,owner='b')
        self.assertEqual(caught.exception.reason,'DEADLINE_EXHAUSTED')
        self.assertEqual(caught.exception.status,'INCOMPLETE')
        self.assertEqual(e._counts['attempted_insertions'],2)
        with self.assertRaises(StudioError):e.snapshot()

    def test_caller_origin_and_earlier_deadline_are_preserved(self):
        e=MeshingEnvelope('coat',{'sampling_calls':3},max_seconds=90,clock=lambda:12.,started_at=5.,deadline=40.)
        self.assertEqual(e.start,5.);self.assertEqual(e.deadline,40.)
        self.assertEqual(e.snapshot()['qualification'],'NONE')

    def test_clock_reversal_and_controlled_stop_refuse(self):
        now=[10.];stop=[False]
        e=MeshingEnvelope('coat',{'sampling_calls':3},clock=lambda:now[0],stop_requested=lambda:stop[0])
        stop[0]=True
        with self.assertRaises(StudioError) as caught:e.reserve('sampling_calls',1)
        self.assertEqual(caught.exception.reason,'STOP_REQUESTED');self.assertEqual(e._counts['sampling_calls'],0)
        stop[0]=False;now[0]=9.
        with self.assertRaises(StudioError) as caught:e.check('test')
        self.assertEqual(caught.exception.reason,'INVALID_CLOCK')

    def test_expiration_after_reservation_keeps_work(self):
        times=iter([0.,0.,0.,10.])
        e=MeshingEnvelope('coat',{'sampling_calls':3},max_seconds=10.,clock=lambda:next(times))
        with self.assertRaises(StudioError):e.reserve('sampling_calls',1)
        self.assertEqual(e._counts['sampling_calls'],1)

    def test_invalid_caps_identity_costs_and_owner_cannot_mutate_work(self):
        for cap in (True,-1,1.5,float('nan')):
            with self.assertRaises(StudioError):MeshingEnvelope('coat',{'x':cap},clock=lambda:0.)
        e=self.make()
        for cost in (True,-1,1.5):
            with self.assertRaises(StudioError):e.reserve('sampling_calls',cost)
        with self.assertRaises(StudioError):e.reserve('undeclared',1)
        with self.assertRaises(StudioError):e.observe_material_controls('another',{'a':['x']})
        with self.assertRaises(StudioError):e.observe_material_controls('coat',{'a':[float('nan')]})
        self.assertTrue(all(value==0 for value in e.snapshot()['work'].values()))

    def test_native_key_coercion_is_refused_before_identity_debit(self):
        e=self.make()
        with self.assertRaises(StudioError) as caught:
            e.observe_material_controls('coat', {'a':[{0:'x'}]})
        self.assertEqual(caught.exception.reason,'INVALID_ENVELOPE')
        self.assertEqual(e.snapshot()['work']['attempted_insertions'],0)
        e.observe_material_controls('coat', {'a':[{'0':'x'}]})
        self.assertEqual(e.material_controls['a'],1)

    def test_strict_identity_containers_and_structure_limits(self):
        cyclic=[];cyclic.append(cyclic)
        deep='x'
        for _ in range(65):deep=[deep]
        for identity in ((1,2), {1,2}, cyclic, deep, [0]*4096,
                         '\ud800', 'x'*4097, float('inf')):
            with self.subTest(kind=type(identity).__name__):
                e=self.make()
                with self.assertRaises(StudioError) as caught:
                    e.observe_material_controls('coat',{'a':[identity]})
                self.assertEqual(caught.exception.reason,'INVALID_ENVELOPE')
                self.assertEqual(e.snapshot()['work']['attempted_insertions'],0)

    def test_clock_failures_are_structured_at_construction(self):
        def failing():raise OSError('clock failure')
        for clock in (None,failing,lambda:None,lambda:10**400,
                      lambda:True,lambda:float('nan')):
            with self.subTest(clock=clock):
                with self.assertRaises(StudioError) as caught:
                    MeshingEnvelope('coat',{'sampling_calls':1},clock=clock)
                self.assertEqual(caught.exception.reason,'INVALID_CLOCK')
                self.assertEqual(caught.exception.status,'REFUSED')
        with self.assertRaises(StudioError) as caught:
            MeshingEnvelope('coat',{'sampling_calls':1},clock=lambda:0.,max_seconds=10**400)
        self.assertEqual(caught.exception.reason,'INVALID_ENVELOPE')

    def test_clock_failure_after_debit_keeps_attempted_work(self):
        calls=[0]
        def clock():
            calls[0]+=1
            if calls[0]==4:raise OSError('clock failure after reservation')
            return 0.
        e=MeshingEnvelope('coat',{'sampling_calls':2},clock=clock)
        with self.assertRaises(StudioError) as caught:e.reserve('sampling_calls',1)
        self.assertEqual(caught.exception.reason,'INVALID_CLOCK')
        self.assertEqual(e._counts['sampling_calls'],1)
        self.assertEqual(e.snapshot()['work']['sampling_calls'],1)

    def test_stop_callback_failure_is_structured_without_debit(self):
        stop=[False]
        def callback():
            if stop[0]:raise OSError('stop callback failure')
            return False
        e=MeshingEnvelope('coat',{'sampling_calls':2},clock=lambda:0.,stop_requested=callback)
        stop[0]=True
        with self.assertRaises(StudioError) as caught:e.reserve('sampling_calls',1)
        self.assertEqual(caught.exception.reason,'INVALID_ENVELOPE')
        self.assertEqual(e._counts['sampling_calls'],0)

if __name__=='__main__':unittest.main()
