"""Geometry-derived guides from declared source face regions, not cut rules.

Region IDs are part of a reviewed asset adapter. Their shared topology produces
joint guides; those guides still require anatomical review. Never infer a region
map from the mannequin's male/female label.
"""
from .core import StudioError, digest


def region_guides(geometry, adapter):
    faces, labels = geometry['faces'], geometry.get('face_sets', [])
    vertices = geometry['vertices_cm']
    if len(labels) != len(faces):
        raise StudioError('Catalog anatomical adapter requires exact source face regions')
    expected = adapter.get('source_geometry_sha256')
    if expected != digest([vertices, faces, labels]):
        raise StudioError('Catalog anatomical adapter is stale for the source topology or metric')
    regions = {}
    for face, label in zip(faces, labels):
        regions.setdefault(label, set()).update(face)
    source = adapter['source_ref']
    if not source:
        raise StudioError('Catalog region mapping must have source provenance')
    guides = {}; evidence = {}
    for name, sides in sorted(adapter['joints'].items()):
        if len(sides) != 2 or sides[0] == sides[1] or any(side not in regions for side in sides):
            raise StudioError('Joint guide needs two distinct actual face regions: '+name)
        shared = regions[sides[0]] & regions[sides[1]]
        if len(shared) < 4:
            raise StudioError('Source regions do not share an anatomical joint ring: '+name)
        # Require a complete topological ring, not vertices touching by chance.
        edges = set()
        for face, label in zip(faces, labels):
            if label != sides[0]:
                continue
            for a, b in zip(face, face[1:]+face[:1]):
                if a in shared and b in shared:
                    edges.add(tuple(sorted((a, b))))
        adjacency = {i: set() for i in shared}
        for a, b in edges:
            adjacency[a].add(b); adjacency[b].add(a)
        if any(len(neighbors) != 2 for neighbors in adjacency.values()):
            raise StudioError('Anatomical joint boundary is not a closed ring: '+name)
        remaining = set(shared); rings = []
        while remaining:
            reached = set(); pending = [min(remaining)]
            while pending:
                i = pending.pop()
                if i not in reached:
                    reached.add(i); pending.extend(adjacency[i]-reached)
            remaining.difference_update(reached); rings.append(reached)
        if len(rings) > 1:
            count = adapter.get('joint_ring_vertex_counts', {}).get(name)
            selected = [ring for ring in rings if len(ring) == count]
            if len(selected) != 1:
                raise StudioError('Anatomical joint has several disconnected rings: '+name)
            shared = selected[0]
        point = [sum(vertices[i][axis] for i in shared)/len(shared) for axis in range(3)]
        guides[name] = {'point_cm': point, 'source_ref': source,
                        'method': 'mean of shared source region boundary vertices',
                        'confidence': 'SOURCE_REGION_GUIDE_REQUIRES_REVIEW'}
        evidence[name] = {'regions': sides, 'boundary_vertices': sorted(shared), 'excluded_source_rings': len(rings)-1}
    for name, selected in sorted(adapter.get('centers', {}).items()):
        if not selected or any(label not in regions for label in selected):
            raise StudioError('Anatomical region center requires actual source regions: '+name)
        ids = set().union(*(regions[label] for label in selected))
        guides[name] = {'point_cm': [sum(vertices[i][axis] for i in ids)/len(ids) for axis in range(3)],
                        'source_ref': source, 'method': 'source region vertex centroid',
                        'confidence': 'SOURCE_REGION_GUIDE_REQUIRES_REVIEW'}
        evidence[name] = {'regions': selected, 'source_vertex_count': len(ids)}
    torso = adapter['torso_regions']
    if not torso or any(label not in regions for label in torso):
        raise StudioError('Anatomical torso segmentation is unavailable')
    return {'rig_landmarks': guides, 'torso_faces': [i for i, label in enumerate(labels) if label in torso],
            'segmentation_source_ref': source, 'joint_evidence': evidence,
            'adapter_sha256': digest(adapter), 'qualification': 'SOURCE_TOPOLOGY_GUIDES_ONLY',
            'source_mutated': False, 'anatomical_review': 'REQUIRED'}
