"""Replay saved detector records through CPU topology/pins; no YOLO/OCR/API call."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from modules.image_io import read_image
from modules.topology import analyze
from modules.pins import attach_pins

ROOT=Path(__file__).resolve().parent.parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--confidences',type=float,nargs='+',default=[.25,.5])
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    records=json.loads(args.predictions.read_text(encoding='utf-8'))
    rows=[]
    data=ROOT/'SINA/Netlist Generator/IC/model_training/data/images/val'
    for record in records:
        image_path=data/record['image']
        image=read_image(image_path)
        if hashlib.sha256(image_path.read_bytes()).hexdigest()!=record['image_sha256']:
            raise ValueError('Frozen image hash mismatch')
        comparisons=[]
        endpoints=[]
        for conf in args.confidences:
            # Stable explicit IDs only within this frozen prediction table.
            boxes=[{'id':'box_'+str(index),'type':box['type'],'bbox':[int(v) for v in box['bbox']]}
                   for index,box in enumerate(record['predictions']) if box['confidence']>=conf]
            start=time.perf_counter()
            try:
                circuit,labels=analyze(image,boxes,args.out/image_path.stem/str(conf),None)
                pins=attach_pins(circuit,labels)
                status_file=args.out/image_path.stem/str(conf)/'crossing_status.json'
                crossing=json.loads(status_file.read_text(encoding='utf-8'))
                nominal={'Resistor':2,'Capacitor':2,'Inductor':2,'Transistor_BJT':3,'Transistor_MOSFET':4,
                         'Voltage_src':2,'Current_src':2,'GND':1,'Diode':2,'Op-Amp':5}
                missing=sum(max(0,nominal.get(c['label'],0)-len(pins[c['id']])) for c in circuit)
                endpoint_map={(cid,tuple(pin['image_point'])): pin['connection_candidate']['region'] if pin['connection_candidate'] else None
                              for cid,contacts in pins.items() for pin in contacts}
                endpoints.append(endpoint_map)
                comparisons.append({'conf':conf,'status':'completed' if crossing['status']=='completed' else 'degraded',
                    'crossing_status':crossing['status'],'nominal_missing_pins':missing,'components':len(circuit),
                    'pins':sum(len(v) for v in pins.values()),'unresolved':sum(pin['connection_candidate'] is None for v in pins.values() for pin in v),
                    'seconds':time.perf_counter()-start})
            except Exception as exc:
                comparisons.append({'conf':conf,'status':'failed','error_type':type(exc).__name__,'seconds':time.perf_counter()-start})
                endpoints.append({})
        row={'image':record['image'],'variants':comparisons}
        if len(endpoints)==2 and all(c['status']=='completed' for c in comparisons):
            common=sorted(set(endpoints[0])&set(endpoints[1]))
            changed=0
            for i,left in enumerate(common):
                for right in common[i+1:]:
                    before=endpoints[0][left] is not None and endpoints[0][left]==endpoints[0][right]
                    after=endpoints[1][left] is not None and endpoints[1][left]==endpoints[1][right]
                    changed+=before!=after
            row.update(common_contacts=len(common),changed_common_connectivity_pairs=changed)
        rows.append(row)
        (args.out/'summary.json').write_text(json.dumps({'images_attempted':len(rows),
            'stage_attempts':sum(len(r['variants']) for r in rows),
            'stage_failures':sum(v['status']!='completed' for r in rows for v in r['variants']),
            'scope':'regression diagnostics, not topology ground-truth accuracy','results':rows},indent=2),encoding='utf-8')
        print(record['image'],comparisons,flush=True)


if __name__=='__main__':
    main()
