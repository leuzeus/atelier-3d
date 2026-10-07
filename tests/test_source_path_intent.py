"""Synthetic provenance probes, never approval of a production garment."""
import copy
import json
import math
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from a3d.core import StudioError, atomic_json, digest, read_json, sha
from a3d.body_source_paths import prepare_project_body_path_review
from a3d.garment_measurements import _assembled_row_topology, _collar_neckline_row
from a3d.source_path_intent import review_source_path_intent
from tests.test_body_source_paths import native_project


def collar_fixture():
    cid = 'garment.fixture'; package = {'path':'package.json','sha256':'a'*64}
    vertices = [[float(i*2),0.] for i in range(7)]+[[12.,2.],[0.,2.]]
    band = {'vertices':vertices,'faces':[[8,i,i+1] for i in range(6)]+[[8,6,7]],
        'edges':{'left':[8,0],'right':[6,7], **{'part.'+str(i):[i,i+1] for i in range(6)}}}
    textiles = {'band':{'component_id':cid,'source_geometry':band,'package_source_ref':package,
        'semantics':{'role':'collar','longitudinal_uv_axis':'u','layer':'outer'}}}
    links = []
    for i in range(6):
        pid = 'inner' if i in (0,5) else 'panel.'+str(i)
        if pid not in textiles:
            geometry = {'vertices':[[0.,0.],[2.,0.],[0.,2.]],'faces':[[0,1,2]],
                        'edges':{'neck':[0,1]}}
            semantics = {'role':'front','guide_edges':{'neck':'neck'},'layer':'outer'}
            if pid == 'inner':
                geometry['edges'] = {'first':[1,0],'last':[2,1]}
                semantics = {'role':'inner_front','guide_edges':{'anchor':'first','anchor_end':'last'},'layer':'outer'}
            textiles[pid] = {'component_id':cid,'source_geometry':geometry,
                             'package_source_ref':package,'semantics':semantics}
        partner = 'first' if i == 0 else 'last' if i == 5 else 'neck'
        links.append({'id':cid+'::join.'+str(i),'source_link_id':'join.'+str(i),
            'component_id':cid,'piece_a':'band','edge_a':'part.'+str(i),'piece_b':pid,
            'edge_b':partner,'orientation':'forward','kind':'permanent','source_ref':package})
    compiled = {'textiles':textiles,'links':links}
    segment = {'piece':'band','from':{'edge':'left','fraction':1.},'to':{'edge':'right','fraction':0.}}
    topology = _assembled_row_topology(compiled,segment)
    attachment = _collar_neckline_row(compiled,'band',0.,[[0.,0.],[12.,0.]])
    assert topology['status'] == 'CLOSED_PERMANENT_ENDPOINT_CYCLE', topology
    return compiled, segment, topology, attachment


def project_fixture(root):
    project, _ = native_project(root)
    prepared = prepare_project_body_path_review(project,'profile.json','specification.json','preparation/body-review')
    body_ref = {'path':'profile.json','sha256':sha(root/'profile.json')}
    report_ref = prepared['artifacts']['report.json']
    report = prepared['report']; path = report['paths'][0]
    def write(path, value):
        atomic_json(root/path,value); return {'path':path,'sha256':sha(root/path)}
    dossier = write('dossier.json',{'explicit_source':'SYNTHETIC'})
    package_ref = write('package.json',{'explicit_source':'SYNTHETIC_SOURCE_GEOMETRY'})
    production_ref = write('production.json',{'source_ref':dossier,'body_ref':body_ref,
        'packages':[{'component_id':'garment.fixture','source_ref':package_ref}]})
    compiled, segment, topology, attachment = collar_fixture()
    for row in compiled['textiles'].values(): row['package_source_ref'] = copy.deepcopy(package_ref)
    for link in compiled['links']: link['source_ref'] = copy.deepcopy(package_ref)
    attachment = _collar_neckline_row(compiled,'band',0.,[[0.,0.],[12.,0.]])
    def evidence(reference): return dict(reference,recorded_at='SYNTHETIC')
    body_gate = {'source':'human','approved':True,'decision_id':'synthetic.body-review',
        'source_ref':'fixture:user:body','statement':'accept this exact source path',
        'evidence':{'body.report':evidence(report_ref)},'timestamp':'SYNTHETIC'}
    context_ref = write('measurement-context.json',{'dossier_ref':dossier,'body_ref':body_ref})
    comparison = {'status':'COLLAR_BODY_REFERENCE_COMPARISON_PREPARED',
        'scope':'HOMOLOGY_AND_NEW_METRIC_INTENT_PROPOSAL_ONLY','body_path_id':path['id'],
        'body_reference_length_cm':path['length_cm'],'body_reference_review':body_gate,
        'source_material_length_cm':12.,'assembled_row_topology':topology,
        'source_neckline_attachment':attachment,'input_refs':[body_ref,report_ref,context_ref],
        'body_changed':False,'patterns_changed':False,'qualification':'NONE','admissible_for_fit':False}
    comparison_ref = write('comparison.json',comparison)
    total = math.fsum((path['length_cm'],4.))
    intent = {'scope':'VARIANT_PREPARATION_TARGET_ONLY','user_statement':'four centimetres total ease',
        'body_reference':comparison_ref,'body_path_id':path['id'],'body_reference_length_cm':path['length_cm'],
        'ease_cm':4.,'target_material_length_cm':total,'source_material_length_cm':12.,
        'ease_decomposition':'NOT_DECLARED','pattern_adoption':'NOT_GRANTED','body_changed':False,'fitting':'NOT_EXECUTED'}
    intent_ref = write('intent.json',intent)
    numeric_gate = {'source':'human','approved':True,'decision_id':'synthetic.target-review',
        'source_ref':'fixture:user:target','statement':intent['user_statement'],
        'evidence':{'intent':evidence(intent_ref),'comparison':evidence(comparison_ref),'body.report':evidence(report_ref)},
        'timestamp':'SYNTHETIC'}
    material = {'domain':'PERMANENT_ENDPOINT_CYCLE','component_id':'garment.fixture','piece':'band',
        'source_geometry_sha256':digest(compiled['textiles']['band']['source_geometry']),
        'source_v_cm':0.,'segments':[segment],'source_material_length_cm':12.,'topology':topology,'attachment':attachment}
    decision = {'status':'SOURCE_PATH_DESIGN_INTENT_APPROVED','approved':True,
        'approved_scope':['assembled_source_path_design_targets'],'component_ids':['garment.fixture'],
        'body_ref':body_ref,'dossier_ref':dossier,'production_specification_ref':production_ref,
        'source_ref':numeric_gate['source_ref'],'statement':numeric_gate['statement'],
        'targets':[{'source_path_ref':comparison_ref,'body_reference_length_cm':path['length_cm'],
            'ease_total_cm':4.,'target_material_length_cm':total,'human_intent_ref':intent_ref,
            'human_review_gate':'review.target','material_reference':material}]}
    state = {'gates':{'review.body':body_gate,'review.target':numeric_gate}}
    def require_gate(current,name):
        for reference in current['gates'][name]['evidence'].values():
            if sha(root/reference['path']) != reference['sha256']: raise StudioError('Synthetic gate stale')
    project.state = lambda:copy.deepcopy(state); project.require_gate = require_gate
    decision_ref = write('decision.json',decision)
    return project, decision, decision_ref, compiled, state


class SourcePathIntent(unittest.TestCase):
    def invoke(self, values):
        project, decision, reference, compiled, _ = values
        with patch('a3d.production_dossier.compile_project_dossier',return_value=compiled) as compiler:
            result = review_source_path_intent(project,decision,reference)
            compiler.assert_called_once_with(project,decision['dossier_ref']['path'],decision['production_specification_ref']['path'])
        return result

    def test_reviewed_nonplanar_length_cycle_and_target_are_remeasured_without_girth_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); values = project_fixture(root)
            before = {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
            inputs = digest([values[1],values[3],values[4]])
            self.assertEqual(self.invoke(values),[{'gate':'review.target','decision_id':'synthetic.target-review','source_ref':'fixture:user:target'}])
            self.assertEqual(inputs,digest([values[1],values[3],values[4]]))
            self.assertEqual(before,{str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()})
            profile = read_json(root/'profile.json')
            self.assertEqual(profile['landmarks']['neck']['girth_cm'],80.)
            self.assertNotEqual(values[1]['targets'][0]['body_reference_length_cm'],80.)

    def test_human_gate_tampering_is_not_an_approval(self):
        for field,value in [('source','agent'),('approved',False),('source_ref','fixture:someone-else'),
                            ('statement','different statement'),('evidence',{})]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                values = project_fixture(Path(directory)); values[4]['gates']['review.target'][field] = value
                with self.assertRaises(StudioError): self.invoke(values)

    def test_changed_intent_file_or_body_file_is_refused(self):
        for name in ('intent.json','profile.json','comparison.json','package.json','dossier.json','production.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = project_fixture(root)
                (root/name).write_bytes((root/name).read_bytes()+b' ')
                with self.assertRaises(StudioError): self.invoke(values)

    def test_changed_numeric_target_bool_nan_or_prior_ease_is_refused(self):
        for field,value in [('ease_total_cm',6.),('target_material_length_cm',1.),
                            ('body_reference_length_cm',80.),('ease_total_cm',True),('ease_total_cm',-1.)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = list(project_fixture(root)); values[1]['targets'][0][field] = value
                atomic_json(root/'decision.json',values[1]); values[2]['sha256'] = sha(root/'decision.json')
                with self.assertRaises(StudioError): self.invoke(values)

    def test_declared_component_or_source_row_cannot_substitute_another_cycle(self):
        for field,value in [('component_id','garment.other'),('source_v_cm',2.),('piece','inner'),
                            ('source_geometry_sha256','f'*64),('domain','CLOSED_GIRTH')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = list(project_fixture(root))
                values[1]['targets'][0]['material_reference'][field] = value
                atomic_json(root/'decision.json',values[1]); values[2]['sha256'] = sha(root/'decision.json')
                with self.assertRaises(StudioError): self.invoke(values)

    def test_changed_permanent_bridge_or_attachment_refuses_forged_report(self):
        for mode in ('closure','detachable','wrong-endpoint','missing-link','extra-proof'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = list(project_fixture(root)); compiled = values[3]
                if mode in ('closure','detachable'): compiled['links'][0]['kind'] = mode
                elif mode == 'wrong-endpoint': compiled['textiles']['inner']['source_geometry']['edges']['first'] = [0,1]
                elif mode == 'missing-link': compiled['links'].pop(2)
                else:
                    values[1]['targets'][0]['material_reference']['topology']['graph_input_sha256'] = 'f'*64
                    atomic_json(root/'decision.json',values[1]); values[2]['sha256'] = sha(root/'decision.json')
                with self.assertRaises(StudioError): self.invoke(values)

    def test_body_path_gate_identity_pose_report_and_file_only_native_are_rejected(self):
        for mode in ('body-gate','pose','report','no-native'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = project_fixture(root)
                if mode == 'body-gate': values[4]['gates']['review.body']['source_ref'] = 'other:review'
                elif mode == 'pose':
                    profile = read_json(root/'profile.json'); profile['pose_sha256'] = 'f'*64; atomic_json(root/'profile.json',profile)
                elif mode == 'report':
                    report = read_json(root/'preparation/body-review/report.json'); report['paths'][0]['length_cm'] += 1.
                    atomic_json(root/'preparation/body-review/report.json',report)
                else:
                    import sqlite3
                    with closing(sqlite3.connect(values[0].db)) as db, db: db.execute('DELETE FROM events')
                with self.assertRaises(StudioError): self.invoke(values)

    def test_duplicate_uncovered_targets_missing_scope_and_terminal_time_are_refused(self):
        for mode in ('duplicate','uncovered','scope','time'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = list(project_fixture(root))
                if mode == 'duplicate': values[1]['targets'].append(copy.deepcopy(values[1]['targets'][0]))
                elif mode == 'uncovered': values[1]['component_ids'].append('garment.other')
                elif mode == 'scope': values[1]['approved_scope'] = []
                atomic_json(root/'decision.json',values[1]); values[2]['sha256'] = sha(root/'decision.json')
                if mode == 'time':
                    with patch('a3d.source_path_intent.time.monotonic',side_effect=[0.,61.]), self.assertRaises(StudioError): self.invoke(values)
                else:
                    with self.assertRaises(StudioError): self.invoke(values)

    def test_other_dossier_copy_and_duplicate_body_review_cannot_qualify(self):
        for mode in ('dossier','duplicate-gate'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = list(project_fixture(root))
                if mode == 'dossier':
                    (root/'other-dossier.json').write_bytes((root/'dossier.json').read_bytes())
                    reference = {'path':'other-dossier.json','sha256':sha(root/'other-dossier.json')}
                    values[1]['dossier_ref'] = reference
                    spec = read_json(root/'production.json'); spec['source_ref'] = reference
                    atomic_json(root/'production.json',spec)
                    values[1]['production_specification_ref']['sha256'] = sha(root/'production.json')
                else:
                    values[4]['gates']['review.body.duplicate'] = copy.deepcopy(values[4]['gates']['review.body'])
                atomic_json(root/'decision.json',values[1]); values[2]['sha256'] = sha(root/'decision.json')
                with self.assertRaises(StudioError): self.invoke(values)

    def test_actual_read_caps_nan_and_terminal_checks(self):
        from a3d.source_path_intent import _IntentBudget
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); values = project_fixture(root)
            # An explicit instance exercises the bound before any JSON parse.
            budget = _IntentBudget(); budget.limits['max_read_bytes'] = 1
            with patch('a3d.source_path_intent._IntentBudget',return_value=budget), self.assertRaisesRegex(StudioError,'reading budget'):
                self.invoke(values)
            changed = copy.deepcopy(values[1]); changed['targets'][0]['ease_total_cm'] = float('nan')
            with self.assertRaises(StudioError): review_source_path_intent(values[0],changed,values[2])
            from a3d.body_source_paths import _Reader
            preserve = _Reader.preserve
            def expire_after_preservation(reader):
                preserve(reader); reader.budget.started -= 61.
            with patch.object(_Reader,'preserve',expire_after_preservation), self.assertRaisesRegex(StudioError,'time budget'):
                self.invoke(values)

    def test_body_or_numeric_gate_revoked_or_replaced_during_preservation_is_refused(self):
        from a3d.body_source_paths import _Reader
        original = _Reader.preserve
        for gate_name, mode in [('review.target','revoked'),('review.body','revoked'),('review.target','replaced')]:
            with self.subTest(gate=gate_name,mode=mode), tempfile.TemporaryDirectory() as directory:
                values = project_fixture(Path(directory))
                def change_gate(reader):
                    original(reader)
                    key = 'approved' if mode == 'revoked' else 'decision_id'
                    values[4]['gates'][gate_name][key] = False if mode == 'revoked' else 'replacement.review'
                with patch.object(_Reader,'preserve',change_gate), self.assertRaisesRegex(StudioError,'review changed'):
                    self.invoke(values)

    def test_duplicate_actual_row_ignores_optional_proofs_numeric_encoding_and_traversal(self):
        for mode in ('proofs','numeric','negative-zero','reverse'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); values = list(project_fixture(root))
                target = copy.deepcopy(values[1]['targets'][0]); material = target['material_reference']
                if mode == 'proofs':
                    for key in ('topology','attachment','source_material_length_cm'): material.pop(key)
                elif mode == 'numeric':
                    material['source_v_cm'] = 0
                    for key in ('from','to'): material['segments'][0][key]['fraction'] = int(material['segments'][0][key]['fraction'])
                elif mode == 'negative-zero': material['source_v_cm'] = -0.0
                else:
                    material['segments'][0]['from'],material['segments'][0]['to'] = material['segments'][0]['to'],material['segments'][0]['from']
                values[1]['targets'].append(target)
                atomic_json(root/'decision.json',values[1]); values[2]['sha256'] = sha(root/'decision.json')
                # Reversal fails the exact reviewed topology before deduplication;
                # the same physical row can never become a second target.
                expected = 'same source path twice' if mode != 'reverse' else 'actual full attached'
                with self.assertRaisesRegex(StudioError,expected): self.invoke(values)

    def test_unrelated_gate_change_does_not_revoke_this_exact_intent(self):
        from a3d.body_source_paths import _Reader
        original = _Reader.preserve
        with tempfile.TemporaryDirectory() as directory:
            values = project_fixture(Path(directory))
            def change_other_gate(reader):
                original(reader); values[4]['gates']['unrelated'] = {'approved':False}
            with patch.object(_Reader,'preserve',change_other_gate):
                self.assertEqual(self.invoke(values)[0]['decision_id'],'synthetic.target-review')


if __name__ == '__main__': unittest.main()
