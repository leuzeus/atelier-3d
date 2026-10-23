"""Native regression for permanent seam supports; optional read-only historical fixture."""
import sys,copy,json,math,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy
from blender.fitting_pose import pose_field
from a3d.core import atomic_json,sha,StudioError
from a3d.sewing import permanent_support_groups
points=[[-1,0,0],[0,0,0],[-1,1,0],[0,1,0],[0,0,0],[1,0,0],[0,1,0],[1,1,0]]
p={'placed_cm':copy.deepcopy(points),'rest_cm':copy.deepcopy(points),'faces':[[0,1,3],[0,3,2],[4,5,7],[4,7,6]],
'panels':{'torso':{'indices':[0,1,2,3],'edges':{}},'sleeve':{'indices':[4,5,6,7],'edges':{'root':[4,6],'wrist':[5,7],'transverse':[6,7]}}},
'pins':{'1':1,'3':1},'seams':{'armhole':{'kind':'permanent','pairs':[[1,4],[3,6]]}}}
frame={'id':'arm','source_ref':'synthetic armhole paired to fixed torso supports','moving_pieces':['sleeve'],
'origin_edges':[{'piece':'sleeve','edge':'root'}],'axis_edges':[{'piece':'sleeve','edge':'wrist'}],
'transverse_edges':[{'piece':'sleeve','edge':'transverse'}],
'target_origin':{'rig':'rig','bone':'arm','endpoint':'head_cm'},'target_axis':{'rig':'rig','bone':'arm','endpoint':'tail_cm'},
'target_transverse_cm':[.5,.5,0],'feather_cm':2,'max_axis_length_difference_cm':.01}
body={'bones':{'rig':{'arm':{'head_cm':[0,.5,.2],'tail_cm':[1,.5,.2]}}}}
recipe={'mesh':{'min_stretch':.8,'max_stretch':1.25,'min_angle_degrees':2,'min_edge_cm':.001},'limits':{'max_displacement_cm':1,'max_seam_gap_cm':.5,'weld_gap_cm':.15}}

source=copy.deepcopy(p);spec={'frames':[frame],'max_displacement_cm':1,'steps':4}
coords,report=pose_field(p,spec,body,recipe)
assert max(math.dist(coords[a],coords[b]) for a,b in [[1,4],[3,6]])<1e-8
assert coords[1]==points[1] and coords[3]==points[3]
assert coords[5]!=points[5] and p==source
assert report['seam_supports']['fixed_groups']==2
assert abs(report['frames'][0]['relaxed_frame_residual_cm']-.2)<1e-8
# Partial supports are preserved as source weights, not promoted to physical pins.
p['pins']={'1':.3,'3':.45};before=copy.deepcopy(p)
q,soft=pose_field(p,spec,body,recipe)
assert q[1]!=points[1] and math.dist(q[1],q[4])<1e-8 and p==before
# A finite source gap keeps its identity under shared rigid-frame influence.
p=copy.deepcopy(source);p['pins']={}
for i in range(4,8):p['placed_cm'][i][0]+=.05;p['rest_cm'][i][0]+=.05
narrow=copy.deepcopy(spec);narrow['frames'][0]['feather_cm']=.1
q,finite=pose_field(p,narrow,body,recipe)
assert abs(math.dist(q[1],q[4])-.05)<1e-8
# Fixed permanent cohorts also remain intact during structural relaxation.
p=copy.deepcopy(source);relaxed=copy.deepcopy(spec)
relaxed['strain_relaxation']={'passes':20,'max_frame_residual_cm':.3}
q,relax=pose_field(p,relaxed,body,recipe)
assert math.dist(q[1],q[4])<1e-8 and q[1]==points[1]
# Reversible closures must not inherit a permanent support or get welded.
p=copy.deepcopy(source);p['seams']['armhole']['kind']='closure'
q,closure=pose_field(p,spec,body,recipe)
assert closure['seam_supports']['permanent_groups']==0 and math.dist(q[1],q[4])>.19
# Native geometric budgets stay strict.
p=copy.deepcopy(source)
for name,change in [('budget',{'max_displacement_cm':.001}),('strain',{})]:
 s=copy.deepcopy(spec);s.update(change);b=copy.deepcopy(body)
 if name=='strain':b['bones']['rig']['arm']['head_cm'][2]+=5;b['bones']['rig']['arm']['tail_cm'][2]+=5;s['max_displacement_cm']=10
 try:pose_field(p,s,b,recipe)
 except StudioError:pass
 else:raise AssertionError('Missing refusal: '+name)
result={'status':'PASS','fixed_pair_gap_cm':report['seam_gap_cm'],'fixed_frame_residual_cm':report['frames'][0]['relaxed_frame_residual_cm'],
 'quality':report['quality'],'fixed_and_partial_supports':'PASS','finite_source_gap':'PRESERVED',
 'closure':'INDEPENDENT','strain_relaxation':'PASS','budget_and_strain_refusals':'PASS',
 'simulation':'NOT_EXECUTED','visual_validation':'NOT_EXECUTED'}
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if args:
 source_path=Path(args[0]).resolve();before_hash=sha(source_path)
 bpy.ops.wm.open_mainfile(filepath=str(source_path),load_ui=False,use_scripts=False)
 obj=bpy.data.objects['TOILE_Buste_Manches'];pairs=json.loads(obj['seam_pairs_json'])
 group=obj.vertex_groups['Construction_supports'];pins={}
 for v in obj.data.vertices:
  for w in v.groups:
   if w.group==group.index:pins[str(v.index)]=w.weight
 payload={'seams':{'historical-permanent':{'kind':'permanent','pairs':pairs}}}
 groups=permanent_support_groups(payload)
 result['historical']={'source':str(source_path),'sha256':before_hash,'source_unchanged':sha(source_path)==before_hash,
  'vertices':len(obj.data.vertices),'declared_pairs':len(pairs),'support_groups':len(groups),
  'fixed_groups':sum(any(pins.get(str(i),0)>=1 for i in ids) for ids in groups),
  'scope':'archived 01f simulation inside 03b; indexed consolidation and 24-frame relaxation; static partial result, not cloth acceptance'}
 assert result['historical']['source_unchanged'] and len(pairs)==161
out=ROOT/('work/native-seam-supports-'+uuid.uuid4().hex);atomic_json(out/'result.json',result)
print(json.dumps({'output':str(out),'result':result}),flush=True)
