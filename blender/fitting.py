"""Read-only native fitting and allocation; no writes or solver loops."""
from a3d.core import StudioError, contract, digest, inside, read_json, sha
from a3d.fitting import compare_fit, propose_adjustments, section_loop


def measured_report(project,obj,payload,recipe,fit_path):
    import bpy
    from blender.sewing import object_mesh,mesh_digest,preflight
    from blender.placement import placement_report
    path=inside(project.root,fit_path);plan=contract('fitting-plan',read_json(path))
    if plan['component_id']!=recipe['component_id']:raise StudioError('Fitting plan component mismatch')
    data=read_json(inside(project.root,payload['source_garment']))
    typed={**data,'seams':[{**s,'kind':recipe['seams'][s['id']]['kind']} for s in data['seams']]}
    sections={};identities={}
    for role in ('body','envelope'):
        sections[role]={};ref=plan.get(role)
        if not ref:continue
        target=bpy.data.objects.get(ref['object'])
        if target is None or target.type!='MESH':raise StudioError('Missing fitting '+role+' object')
        if abs(bpy.context.scene.unit_settings.scale_length-1)>1e-8 or any(abs(s-1)>1e-6 for s in target.scale):
            raise StudioError('Fitting requires meters and applied object scale')
        current=mesh_digest(target,True)
        if current!=ref['geometry_sha256']:raise StudioError('Fitting '+role+' geometry/pose changed')
        if role=='envelope' and not any(c['object']==target.name and c['geometry_sha256']==current for c in recipe['colliders']):
            raise StudioError('Fitting envelope is not the actual recipe collider')
        vertices,faces=object_mesh(target,True);vertices=[[x*100 for x in p] for p in vertices]
        identities[role]={'object':target.name,'geometry_sha256':current,'role':ref['role']}
        for row in plan['measurements']:
            section=row.get(role+'_section')
            if section:sections[role][row['id']]=section_loop(vertices,faces,section)
    report=compare_fit(typed,plan,sections['body'],sections['envelope'])
    context,_,trees=preflight(obj,payload,recipe)
    placement=placement_report(obj,payload,recipe,context,trees,project.root)
    placement_summary={'warnings':placement['warnings'],
        'seams':{sid:{k:s[k] for k in ('kind','max_gap_cm','segments_crossing_collider')} for sid,s in placement['seams'].items()},
        'interpretation':placement['interpretation']}
    report.update(component_id=recipe['component_id'],fit_plan={'path':fit_path,'sha256':sha(path)},
        identities=identities,package_sha256=payload['package_sha256'],source_garment_sha256=payload['source_garment_sha256'],
        recipe_sha256=digest(recipe),boundary_map_sha256=obj['a3d_sewing_mesh_sha256'],
        placement_diagnosis=placement_summary,
        support_diagnosis={'pins':recipe['pins'],'temporary_closures':[t['seam_id'] for t in recipe.get('fitting_tacks',[])],
            'unheld_closures':[sid for sid,s in recipe['seams'].items() if s['kind']=='closure' and sid not in {t['seam_id'] for t in recipe.get('fitting_tacks',[])}],
            'cause_of_cloth_failure':'NOT_ESTABLISHED'},
        diagnoses={'cut':report['fit_status'],'placement':'SIGNALS_OBSERVED' if any(placement['warnings'].values()) else 'NO_DECLARED_INITIAL_SIGNAL',
            'support':'DECLARED_NOT_PROVEN','physics':'NOT_ESTABLISHED'})
    report['fit_binding']=digest({'plan_sha256':sha(path),'identities':identities,'source':payload['source_garment_sha256'],
        'package':payload['package_sha256'],'recipe':digest(recipe)})
    return report,typed,plan


def recipe_fit(project,obj,payload,recipe):
    ref=recipe.get('fitting_plan')
    if not ref:return None
    if sha(inside(project.root,ref['path']))!=ref['sha256']:raise StudioError('Referenced fitting plan changed; update the recipe and requalify')
    return measured_report(project,obj,payload,recipe,ref['path'])[0]


def inspect_garment_fit(project_root,component_id,recipe_path,fit_path):
    from blender.operations import working
    from blender.sewing import managed_inputs
    project,_=working(project_root);obj,payload,recipe=managed_inputs(project,component_id,recipe_path)
    return measured_report(project,obj,payload,recipe,fit_path)[0]


def propose_pattern_adjustment(project_root,component_id,recipe_path,fit_path):
    from blender.operations import working
    from blender.sewing import managed_inputs
    project,_=working(project_root);obj,payload,recipe=managed_inputs(project,component_id,recipe_path)
    report,data,plan=measured_report(project,obj,payload,recipe,fit_path)
    proposal=propose_adjustments(data,plan,report)
    return {**proposal,'measurement_report':report,'fit_binding':report['fit_binding']}
