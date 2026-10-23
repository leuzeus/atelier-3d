"""Admission for legacy static-body textile physics, separate from acceptance."""
from .core import StudioError, contract, inside, read_json


def require_recipe_fit_intent(project, recipe):
    """Reject body trials without exact reviewed source intent before effects.

    Collider-free assembly remains a source construction experiment. Explicit
    TEST_ONLY body trials never create a production fitting qualification.
    """
    contract('sewing-recipe', recipe)
    bodies = [row for row in recipe['colliders'] if row['role'] == 'mannequin']
    purpose = recipe.get('physics_purpose')
    if not recipe['colliders'] and purpose is None:
        return {'purpose': purpose or 'SOURCE_ASSEMBLY',
                'admission': 'SOURCE_ASSEMBLY_WITHOUT_BODY', 'fitting': 'NOT_QUALIFIED',
                'product_acceptance': 'NOT_GRANTED', 'accepted': False}
    if purpose == 'TEST_ONLY':
        if recipe.get('fit_context') is not None:
            raise StudioError('TEST_ONLY body physics cannot carry a production fit context')
        return {'purpose': purpose, 'admission': 'TEST_ONLY_BODY_EXPERIMENT',
                'fitting': 'NOT_QUALIFIED', 'product_acceptance': 'NOT_GRANTED', 'accepted': False}
    if purpose != 'GARMENT_CANDIDATE' or recipe.get('fit_context') is None:
        raise StudioError('Body textile physics requires explicit purpose and reviewed fit_context classification and numeric ease')
    if len(bodies) != 1:
        raise StudioError('Production static-body physics requires one exact measured body collider')
    context = recipe['fit_context']
    from .native_evidence import checked_reference
    for reference in context.values(): checked_reference(project, reference)
    compiled = read_json(inside(project.root, context['compiled_dossier_ref']['path']))
    cid = recipe['component_id']
    sources = [row['package_source_ref'] for row in compiled['components']
               if row['id'] == cid and row['pipeline'] == 'PATTERN_SEWN']
    canonical = project.state()['components'][cid]['package']
    package_ref = {key: canonical[key] for key in ('path', 'sha256')}
    if sources != [package_ref]:
        raise StudioError('Reviewed fit intent differs from the exact executing canonical source package')
    checked_reference(project, package_ref)
    from .garment_fit import require_fit_intent
    report = require_fit_intent(project, context['compiled_dossier_ref']['path'], context['fit_profile_ref']['path'])
    if cid not in {row['component_id'] for row in report['checks']}:
        raise StudioError('Body textile physics component has no measured path in the reviewed fit intent')
    specification = read_json(inside(project.root, context['fit_profile_ref']['path']))
    return {'purpose': purpose, 'admission': 'EXPLORATORY_PHYSICS_ONLY',
            'fit_context': context, 'fit_intent': report, 'body_ref': specification['body_ref'],
            'package_ref': package_ref,
            'body_collider': bodies[0]['object'], 'fitting': 'NOT_QUALIFIED',
            'product_acceptance': 'NOT_GRANTED', 'accepted': False}
