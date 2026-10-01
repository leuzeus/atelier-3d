# Fixtures de contrats

Ces données sont synthétiques. Les petits PNG uniformes servent à vérifier le format, les dimensions et les empreintes ; ils ne représentent pas un squelette et ne doivent jamais être envoyés pour une production réelle.

- garment-coat : panneaux avant/arrière et manches, géométrie SVG/JSON explicite, coutures indexées.
- articulated-skeleton : crâne, mâchoire et thorax séparés, relations hinged et parented, packages front/left distincts par composant.

Les tests assemblent et extraient les archives, valident les identités et vérifient le routage. Ils ne constituent pas les deux golden fixtures visuelles finales demandées par la spécification. Celles-ci exigent des références réelles, une reconstruction qualifiée, une simulation Cloth et une validation dans Blender ; voir VALIDATION.md.
