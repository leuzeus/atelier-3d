"""Deterministic labels and fabrication lines around the Codex Image illustration."""
import base64
import html
import math
import textwrap
from .core import inside
from .packages import png_dimensions
from .board_contract import at_edge, inside_polygon, pieces, project_segment, distance, assembly_mark_position


def render(project, dossier, garments, source_refs):
    escape=lambda value: html.escape(str(value), quote=True)
    parts=[]
    def text(x,y,value,cls="small"):
        parts.append(f'<text x="{x:.2f}" y="{y:.2f}" class="{cls}">{escape(value)}</text>')
    def lines(value,width=48):
        return textwrap.wrap(str(value),width=width,break_long_words=True,break_on_hyphens=False) or [""]
    def paragraphs(x,y,values,width=48,step=23,cls="small"):
        for value in values:
            for line in lines(value,width):
                text(x,y,line,cls); y+=step
        return y
    def data(path):
        payload=inside(project.root,path).read_bytes()
        return "data:image/png;base64,"+base64.b64encode(payload).decode(),png_dimensions(payload)
    def image(x,y,w,h,path):
        uri,(pw,ph)=data(path)
        scale=min(w/pw,h/ph)
        ox=x+(w-pw*scale)/2; oy=y+(h-ph*scale)/2
        parts.append(f'<image x="{ox}" y="{oy}" width="{pw*scale}" height="{ph*scale}" href="{uri}"/>')
        return ox,oy,scale
    all_pieces=pieces(dossier)
    names=[]
    for index,(cid,p) in enumerate(all_pieces,1):
        values=[f"A{index:02} — {p['label']}",f"{cid}/{p['id']}",f"Matière : {p['material']}",
            ' × '.join(f'{n:g}' for n in p['dimensions_cm'])+' cm (patron/volume à plat)',*p['characteristics']]
        names.append(values)
    name_rows=[]
    for offset in range(0,len(names),3):
        row=names[offset:offset+3]
        name_rows.append(max(sum(len(lines(t,36)) for t in values) for values in row)*23+30)
    top_end=max(980,885+sum(name_rows))
    panels=[(cid,p,garments[cid]["pieces"][p["id"]]) for cid,p in all_pieces if cid in garments]
    panel_notes=[]
    bounds=[]
    for cid,p,g in panels:
        v=p["pattern"]["cut_outline_cm"]
        lo=[min(q[i] for q in v) for i in (0,1)]
        size=[max(q[i] for q in v)-lo[i] for i in (0,1)]
        bounds.append((lo,size))
        panel_notes.append([f"Couper ×{p['pattern']['cut_quantity']} — {p['pattern']['cut_instruction']}",
            f"{p['material']} • couture {p['dimensions_cm'][0]:g} × {p['dimensions_cm'][1]:g} cm",
            f"Marge de coupe : {p['seam_allowance_cm']:g} cm • {p['basis']}",p['pattern']['fold_notes']])
    common_scale=min(495/max(s[0] for _,s in bounds),240/max(s[1] for _,s in bounds)) if panels else 1
    header_height=53+23*max((len(lines(p['label'],48)) for _,p,_ in panels),default=1)
    plot_top=header_height+20
    plot_bottom=plot_top+240
    notes_top=plot_bottom+30
    card_height=notes_top+40+max((sum(len(lines(t,54)) for t in notes)*23 for notes in panel_notes),default=90)
    pattern_y=top_end+200
    source_y=pattern_y+max(1,math.ceil(len(panels)/4))*card_height+25
    height=source_y+math.ceil(len(source_refs)/3)*270+80
    parts.extend([f'<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="{height}" viewBox="0 0 2400 {height}">',
        '<style>text{font-family:Segoe UI,Arial,sans-serif;fill:#183246}.title{font-size:36px;font-weight:700}.section{font-size:26px;font-weight:700}.small{font-size:18px}.label{font-size:21px;font-weight:600}.micro{font-size:15px}</style>',
        '<defs><marker id="grain-arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#25485e"/></marker></defs>',
        f'<rect width="2400" height="{height}" fill="#f4f6f7"/>'])
    text(30,48,dossier['title'],'title')
    text(30,82,f"PROPOSITION À VALIDER PAR UN HUMAIN • Gabarit {dossier['height_cm']:g} cm • Base : images originales • unités cm")
    text(30,125,"1. VUES ORTHOGRAPHIQUES",'section')
    text(1120,125,"2. DÉCOMPOSITION DU VÊTEMENT — CODEX IMAGE",'section')
    ortho=dossier['orthographic']
    ortho_scale=min(620/ortho['front']['subject_height_cm'],min(325/(v['subject_bbox_px'][2]/v['subject_bbox_px'][3]*v['subject_height_cm']) for v in ortho.values()))
    for index,(key,label) in enumerate((('front','Face'),('side','Profil'),('back','Dos'))):
        view=ortho[key]; uri,(w,h)=data(view['path']); bx,by,bw,bh=view['subject_bbox_px']
        sh=view['subject_height_cm']*ortho_scale; sw=bw/bh*sh
        x=30+index*355+(325-sw)/2; y=160+620-sh
        parts.append(f'<svg x="{x}" y="{y}" width="{sw}" height="{sh}" viewBox="{bx} {by} {bw} {bh}" overflow="hidden"><image width="{w}" height="{h}" href="{uri}"/></svg>')
        text(30+index*355,815,label+' — '+view['basis'],'label')
    paragraphs(30,866,["Vues cadrées et affichées à une échelle commune.","Les parties cachées et dimensions extrapolées restent à confirmer.",
        f"{len(dossier['proportion_checks'])} contrôles de rapports dimensionnels renseignés.","Comparer particulièrement manches, poignets, capuche et ouverture des pans.",
        "La validation du découpage ne vaut pas validation du drapé."],88,28)
    ox,oy,scale=image(1130,155,1210,625,dossier['exploded']['path'])
    anchors={(a['component_id'],a['piece_id']):a for a in dossier['exploded']['annotations']}
    for index,(cid,p) in enumerate(all_pieces,1):
        annotation=anchors[cid,p['id']]
        ax,ay=annotation['anchor_px']; px,py=ox+ax*scale,oy+ay*scale
        lx,ly=annotation['label_position_px']; lx,ly=ox+lx*scale,oy+ly*scale
        label=lines(f'A{index:02} — '+p['label'],30)
        label_width=max(len(line) for line in label)*8.8+12
        label_height=len(label)*19+8
        parts.append(f'<path class="piece-callout" d="M {px} {py} L {lx} {ly}" stroke="#50687b" stroke-width="1.5" fill="none"/>')
        parts.append(f'<rect x="{lx-4}" y="{ly-17}" width="{label_width}" height="{label_height}" fill="white" fill-opacity="0.95"/>')
        for i,line in enumerate(label): text(lx,ly+i*19,line,'micro')
        parts.append(f'<circle cx="{px}" cy="{py}" r="20" fill="white" stroke="#284e69" stroke-width="2"/>')
        text(px-17,py+6,f'A{index:02}','micro')
    text(1120,817,"NOMENCLATURE — repères identiques dans l’éclaté et les patrons",'label')
    y=860
    for row_index,row_height in enumerate(name_rows):
        for col,values in enumerate(names[row_index*3:row_index*3+3]):
            x=1120+col*415
            parts.append(f'<rect x="{x}" y="{y-22}" width="395" height="{row_height-12}" fill="white" stroke="#c8d2da"/>')
            paragraphs(x+10,y,values,36)
        y+=row_height
    text(30,top_end+20,"3. PATRONS 2D DE FABRICATION" if panels else "3. CONSTRUCTION PAR PIÈCE — SANS PATRONS TEXTILES",'section')
    text(30,top_end+52,"Coupe : trait continu • Couture / piqûre : tirets • Pli / milieu : trait mixte • Droit-fil : double flèche • Assemblage : crans appariés")
    text(30,top_end+80,"Même échelle pour tous les patrons ; ne pas imprimer ce board comme un patron 1:1. Les coordonnées en cm font foi.")
    if panels:
        # Scale bar uses exactly the same cm-to-pixel factor as every panel.
        length=50 if 50*common_scale<450 else 10
        parts.append(f'<path d="M 30 {top_end+107} v 10 h {length*common_scale} v -10" fill="none" stroke="#284e69" stroke-width="2"/>')
        text(40+length*common_scale,top_end+117,f'{length:g} cm — échelle commune')
    text(30,top_end+152,"Les lignes et repères proviennent des données de coupe et des coutures ; l’illustration générée ne dessine pas ces patrons.")
    for index,(cid,p,g) in enumerate(panels):
        x=30+(index%4)*590; y=pattern_y+(index//4)*card_height
        parts.append(f'<rect x="{x}" y="{y}" width="570" height="{card_height-18}" rx="8" fill="white" stroke="#c8d2da"/>')
        number=next(i for i,(c,q) in enumerate(all_pieces,1) if c==cid and q['id']==p['id'])
        paragraphs(x+12,y+28,[f"A{number:02} — {p['label']}"],48,23,'label')
        text(x+12,y+header_height-12,f"{cid}/{p['id']}",'micro')
        lo,size=bounds[index]; ox=x+285-size[0]*common_scale/2; oy=y+plot_top+size[1]*common_scale
        coords=lambda pt:(ox+(pt[0]-lo[0])*common_scale,oy-(pt[1]-lo[1])*common_scale)
        points=lambda vs:' '.join(f'{a:.3f},{b:.3f}' for a,b in map(coords,vs))
        outline=p['pattern']['cut_outline_cm']
        parts.append(f'<polygon data-piece="{escape(cid+"/"+p["id"])}" data-scale="{common_scale}" points="{points(outline)}" fill="#e7edf1" stroke="#284e69" stroke-width="2"/>')
        parts.append(f'<path class="stitch-line" d="M {points(g["vertices"])} Z" fill="none" stroke="#815329" stroke-width="1.8" stroke-dasharray="5 4"/>')
        for seam_index,seam in enumerate(garments[cid]['seams'],1):
            for side in ('a','b'):
                if seam['piece_'+side]!=p['id']: continue
                indexes=g['edges'][seam['edge_'+side]]
                parts.append(f'<polyline class="seam-edge" points="{points([g["vertices"][i] for i in indexes])}" fill="none" stroke="#815329" stroke-width="2" stroke-dasharray="5 4"/>')
                for mark in p['pattern']['assembly_marks']:
                    if mark['seam_id']!=seam['id']: continue
                    mark_point=at_edge(g['vertices'],indexes,assembly_mark_position(mark,seam,side))
                    cut_point=min((project_segment(mark_point,a,b) for a,b in zip(outline,outline[1:]+outline[:1])),key=lambda p:distance(mark_point,p))
                    ax,ay=coords(cut_point)
                    for offset in ((0,7) if mark['symbol']=='double-notch' else (0,)):
                        parts.append(f'<path class="assembly-notch" d="M {ax-5+offset} {ay-6} L {ax+offset} {ay+3} L {ax+5+offset} {ay-6} Z" fill="#354e62"/>')
                    text(max(x+12,min(x+490,ax+8)),max(y+plot_top,min(y+plot_bottom,ay+17)),f'S{seam_index:02}/{mark["id"]}','micro')
        for fold in p['pattern']['folds']:
            parts.append(f'<polyline class="fold-line" points="{points(fold["line_cm"])}" fill="none" stroke="#806294" stroke-width="2" stroke-dasharray="12 5 2 5"/>')
            ax,ay=coords(fold['line_cm'][0]); text(max(x+12,min(x+420,ax+5)),max(y+plot_top,min(y+plot_bottom,ay-4)),fold['id']+' — '+fold['label'],'micro')
        vertices=g['vertices']; center=[(min(v[i] for v in vertices)+max(v[i] for v in vertices))/2 for i in (0,1)]
        if not inside_polygon(center,vertices): center=vertices[0]
        cx,cy=coords(center); gx,gy=p['grain_direction']; norm=math.hypot(gx,gy); arrow=min(40,max(size)*common_scale*.22)
        dx,dy=gx/norm*arrow,-gy/norm*arrow
        parts.append(f'<path class="grain-direction" d="M {cx-dx} {cy-dy} L {cx+dx} {cy+dy}" stroke="#25485e" stroke-width="2" marker-start="url(#grain-arrow)" marker-end="url(#grain-arrow)"/>')
        text(max(x+12,min(x+470,cx+9)),max(y+plot_top+12,min(y+plot_bottom,cy)),"Droit-fil",'micro')
        paragraphs(x+12,y+notes_top,panel_notes[index],54)
    if not panels: text(30,pattern_y+40,"Route MULTIVIEW_PART : détails des volumes, ancrages et interfaces dans le dossier technique.")
    text(30,source_y+25,"RÉFÉRENCES ORIGINALES — base de la conception",'label')
    for index,(key,source) in enumerate(source_refs.items()):
        x=30+(index%3)*790; y=source_y+45+(index//3)*270
        image(x,y,745,210,source['evidence']['path']); text(x,y+238,key)
    parts.append('</svg>')
    return '\n'.join(parts)
