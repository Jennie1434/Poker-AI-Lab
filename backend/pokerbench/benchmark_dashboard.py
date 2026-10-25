"""Build a standalone, offline comparison dashboard from completed experiments."""
import argparse
import json
from pathlib import Path


TEMPLATE = '''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Poker AI Lab · Benchmarks</title>
<style>
body{font:16px system-ui;margin:0;background:#f3f5f7;color:#182634}main{max-width:1250px;margin:auto;padding:32px}h1{margin-bottom:8px}p{max-width:950px;line-height:1.6}select,button{font:inherit;padding:8px}label{margin-right:20px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;background:white;margin-top:24px}th,td{text-align:right;padding:12px;border-bottom:1px solid #dee3e8;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{background:#e6edf2}#bars{background:white;margin:24px 0;padding:18px}.bar-row{display:grid;grid-template-columns:200px 1fr;align-items:center}.bar-row svg{width:100%;height:42px}.note{color:#465b6c;font-size:14px}footer{margin-top:24px}a{color:#136d64}
</style></head><body><main>
<h1>Poker AI Lab · Benchmarks heads-up</h1>
<p>Politiques fixes, 200 BB par main, positions alternées et donnes indépendantes. Les intervalles à 95 % décrivent l'incertitude sur la moyenne ; ils ne prouvent pas la supériorité générale d'un agent.</p>
<label>Résultats <select id="metric"><option value="net">Nets de rake</option><option value="gross">Bruts</option></select></label>
<label>Expérience <select id="experiment"><option value="all">Toutes</option></select></label>
<div id="bars" aria-label="Profits bb/100 et intervalles de confiance"></div>
<div class="scroll"><table><thead><tr><th>Expérience / agent</th><th>Mains</th><th>BTN / BB</th><th>Profit (BB)</th><th>bb/100</th><th>IC 95 %</th><th>Mains gagnantes</th><th>Mains à zéro</th></tr></thead><tbody id="results"></tbody></table></div>
<div id="settings"></div>
<footer class="note">IC normal asymptotique sur les moyennes de blocs indépendants de deux mains (une par position). Mains gagnantes = profit strictement positif, différent de l'équité ou du taux de showdowns gagnés. Le rake est une simulation comptable sur les décisions inchangées, hors mises non suivies. Les cartes et journaux de décisions ne sont pas inclus dans cette page. Comparer uniquement des protocoles compatibles ; les résultats sur un adversaire ne constituent pas un classement universel.</footer>
<script id="data" type="application/json">__DATA__</script>
<script>
const reports=JSON.parse(document.getElementById('data').textContent);
const selector=document.getElementById('experiment');
reports.forEach((r,i)=>{const o=document.createElement('option');o.value=String(i);o.textContent=r.name;selector.append(o);});
const fmt=(v,d=2)=>Number(v).toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d});
function render(){
 const metric=document.getElementById('metric').value;
 const selected=reports.filter((r,i)=>selector.value==='all'||selector.value===String(i));
 const rows=selected.flatMap(r=>Object.entries(r.summary.agents).map(([seat,a])=>({name:r.name+' / '+a.policy+' ('+seat+')',agent:a,stats:a[metric],hands:r.summary.completed_hands})));
 const tbody=document.getElementById('results');tbody.replaceChildren();
 rows.forEach(r=>{const tr=document.createElement('tr');const s=r.stats;[r.name,r.hands,r.agent.button_hands+' / '+r.agent.big_blind_hands,fmt(s.profit_bb),fmt(s.bb_per_100),s.ci95_bb_per_100.map(x=>fmt(x)).join(' à '),fmt(100*s.win_rate)+' %',fmt(100*s.break_even_rate)+' %'].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td);});tbody.append(tr);});
 const bars=document.getElementById('bars');bars.replaceChildren();
 const max=Math.max(1,...rows.flatMap(r=>r.stats.ci95_bb_per_100.map(Math.abs)))*1.1;
 const x=v=>400+v/max*390;
 const ns='http://www.w3.org/2000/svg';
 rows.forEach(r=>{const div=document.createElement('div');div.className='bar-row';const label=document.createElement('span');label.textContent=r.name;div.append(label);const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 800 42');svg.setAttribute('role','img');const title=document.createElementNS(ns,'title');title.textContent=r.name+': '+fmt(r.stats.bb_per_100)+' bb/100';svg.append(title);function line(a,b,color,width){const l=document.createElementNS(ns,'line');Object.entries({x1:x(a),x2:x(b),y1:21,y2:21,stroke:color,'stroke-width':width}).forEach(([k,v])=>l.setAttribute(k,v));svg.append(l);}line(-max,max,'#e6edf2',1);line(0,r.stats.bb_per_100,r.stats.bb_per_100>=0?'#138474':'#c85844',12);line(...r.stats.ci95_bb_per_100,'#182634',3);const zero=document.createElementNS(ns,'line');Object.entries({x1:400,x2:400,y1:2,y2:40,stroke:'#697887'}).forEach(([k,v])=>zero.setAttribute(k,v));svg.append(zero);div.append(svg);bars.append(div);});
 const settings=document.getElementById('settings');settings.replaceChildren();
 selected.forEach(r=>{const p=document.createElement('p');p.className='note';p.textContent=r.name+' — '+r.config.hands+' mains ; rake '+r.config.rake_percent+' %, plafond '+r.config.rake_cap_bb+' BB, no-flop-no-drop '+(r.config.no_flop_no_drop?'oui':'non')+' ; prélèvement total '+fmt(r.summary.rake_chips/100)+' BB ; '+r.config.equity_samples+' échantillons par estimation d’équité.';settings.append(p);});
}
selector.addEventListener('change',render);document.getElementById('metric').addEventListener('change',render);render();
</script></main></body></html>'''


def build(reports: list[Path], output: Path):
    data = []
    for path in reports:
        report = json.loads(path.read_text())
        if report.get("status") != "complete":
            raise ValueError("Only completed experiments can be compared")
        data.append({"name": path.parent.name, "config": report["config"], "summary": report["summary"]})
    if not data:
        raise ValueError("At least one experiment is required")
    # Do not embed private traces, provenance seeds outside config, or arbitrary HTML.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    with output.open("x") as f:
        f.write(TEMPLATE.replace("__DATA__", payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.reports, args.output)


if __name__ == "__main__":
    main()
