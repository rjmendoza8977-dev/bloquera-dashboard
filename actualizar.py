#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bloquera Fúnez — Actualizador de Dashboard
==========================================
1. Pon el archivo .aks de Akasia en la carpeta /datos/
2. Doble clic en este archivo (actualizar.py)
3. Se abre el dashboard actualizado en el navegador

Requisitos: Python 3.8+  (sin librerías externas)
"""

import os, re, json, sys, glob, webbrowser, shutil, io
from datetime import datetime, date
from collections import defaultdict

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Configuración ──────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR   = os.path.join(BASE_DIR, "datos")
TEMPLATE    = os.path.join(BASE_DIR, "bloquera-funez-template.html")
OUTPUT      = os.path.join(BASE_DIR, "bloquera-funez.html")
GASTOS_FILE = os.path.join(BASE_DIR, "gastos.json")   # gastos manuales (opcional)

MESES_ES = {
    1:"Ene", 2:"Feb", 3:"Mar", 4:"Abr", 5:"May", 6:"Jun",
    7:"Jul", 8:"Ago", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dic"
}

# ── 1. Encontrar el archivo .aks más reciente ──────────────────
def find_aks():
    files = glob.glob(os.path.join(DATOS_DIR, "*.aks"))
    if not files:
        print("ERROR: No se encontró ningún archivo .aks en la carpeta /datos/")
        print("       Descarga el respaldo de Akasia y pégalo en:")
        print(f"       {DATOS_DIR}")
        input("\nPresiona ENTER para cerrar...")
        sys.exit(1)
    latest = max(files, key=os.path.getmtime)
    print(f"✓ Archivo encontrado: {os.path.basename(latest)}")
    return latest

# ── 2. Parsear SQL dump (formato Akasia: INSERT header + value rows) ──────────
def parse_inserts(lines, table_name):
    """
    Formato Akasia:
      INSERT INTO `table`(col1,col2,...)\n
      (val1,val2,...)\n
      (val1,val2,...)\n
      ...
    """
    rows = []
    cols = []
    collecting = False

    insert_pat = re.compile(
        r"INSERT INTO `" + re.escape(table_name) + r"`\(([^)]+)\)", re.IGNORECASE
    )

    for line in lines:
        line = line.rstrip('\n\r')

        # Detect INSERT header
        m = insert_pat.match(line)
        if m:
            cols = [c.strip().strip('`') for c in m.group(1).split(',')]
            collecting = True
            continue

        if collecting:
            stripped = line.strip()
            if stripped.startswith('('):
                # Remove trailing comma/semicolon
                stripped = stripped.rstrip(',;').rstrip()
                # Remove outer parens
                if stripped.endswith(')'):
                    inner = stripped[1:-1]
                else:
                    inner = stripped[1:]
                vals = parse_tuple(inner)
                if len(vals) == len(cols):
                    rows.append(dict(zip(cols, vals)))
            elif stripped == '' or stripped.startswith('--') or stripped.startswith('/*'):
                collecting = False
    return rows

def parse_tuple(tup):
    """Parsea valores de una tupla SQL respetando strings con comas y escapes."""
    vals = []
    current = ''
    in_str = False
    i = 0
    while i < len(tup):
        ch = tup[i]
        if ch == '\\' and in_str and i+1 < len(tup):
            current += ch + tup[i+1]
            i += 2
            continue
        if ch == "'" and not in_str:
            in_str = True
        elif ch == "'" and in_str:
            # Check for escaped quote ''
            if i+1 < len(tup) and tup[i+1] == "'":
                current += "'"
                i += 2
                continue
            in_str = False
        elif ch == ',' and not in_str:
            vals.append(current.strip().strip("'"))
            current = ''
            i += 1
            continue
        else:
            current += ch
        i += 1
    vals.append(current.strip().strip("'"))
    return vals

def safe_float(v):
    try: return float(v) if v not in ('NULL', None, '') else 0.0
    except: return 0.0

def safe_date(v):
    """Extrae YYYY-MM-DD de un datetime string."""
    if not v or v == 'NULL': return None
    return str(v)[:10]

# ── 3. Agregar datos por mes ───────────────────────────────────
def build_monthly(ventas, venta_productos):
    """
    Retorna:
    - monthly: dict {YYYY-MM: {ventas, costo, dias_set, productos: {nombre: {ventas, costo, qty}}}}
    - daily:   dict {YYYY-MM-DD: {ventas, costo}}
    """
    # Mapa uuid_venta → fecha, total, is_active
    venta_map = {}
    for v in ventas:
        uid  = v.get('uuid_venta') or v.get('vUUIDVenta','')
        fec  = safe_date(v.get('f_alta',''))
        tot  = safe_float(v.get('total', 0))
        baja = v.get('f_baja','NULL')
        act  = v.get('is_active','1')
        if baja not in ('NULL','') or act == '0':
            continue   # venta cancelada
        if uid and fec:
            venta_map[uid] = {'fecha': fec, 'total': tot}

    monthly  = defaultdict(lambda: {
        'ventas':0.0,'costo':0.0,'dias': set(),
        'productos': defaultdict(lambda: {'ventas':0.0,'costo':0.0,'qty':0})
    })
    daily    = defaultdict(lambda: {'ventas':0.0,'costo':0.0})

    for vp in venta_productos:
        uid   = vp.get('uuid_venta','')
        if uid not in venta_map:
            continue
        fecha = venta_map[uid]['fecha']   # YYYY-MM-DD
        mes   = fecha[:7]                  # YYYY-MM
        nombre= vp.get('nombre_producto','').strip()
        importe= safe_float(vp.get('importe',0))
        costo = safe_float(vp.get('precio_compra',0)) * safe_float(vp.get('cantidad',0))
        qty   = safe_float(vp.get('cantidad',0))
        active= vp.get('is_active','1')
        if active == '0':
            continue

        monthly[mes]['ventas']              += importe
        monthly[mes]['costo']               += costo
        monthly[mes]['dias'].add(fecha)
        monthly[mes]['productos'][nombre]['ventas'] += importe
        monthly[mes]['productos'][nombre]['costo']  += costo
        monthly[mes]['productos'][nombre]['qty']    += qty

        daily[fecha]['ventas'] += importe
        daily[fecha]['costo']  += costo

    return monthly, daily

# ── 4. Construir JS data ───────────────────────────────────────
def build_js(monthly, daily, gastos_ext):
    meses_sorted = sorted(monthly.keys())  # YYYY-MM order
    # Últimos 7 meses (o menos)
    meses_sorted = meses_sorted[-7:]

    def mes_label(ym):
        y, m = ym.split('-')
        return f"{MESES_ES[int(m)]} {y}"

    labels     = [mes_label(m) for m in meses_sorted]
    ventas_m   = [round(monthly[m]['ventas'])  for m in meses_sorted]
    costo_m    = [round(monthly[m]['costo'])   for m in meses_sorted]
    ub_m       = [v - c for v, c in zip(ventas_m, costo_m)]

    # Gastos mensuales — desde gastos.json si existe, si no 0
    gastos_m = []
    gastos_por_mes_js = {}
    for m in meses_sorted:
        g_list = gastos_ext.get(m, [])
        total_g = sum(x['monto'] for x in g_list)
        gastos_m.append(total_g)
        if g_list:
            gastos_por_mes_js[f"'{m}'"] = json.dumps(g_list, ensure_ascii=False)

    # Daily data (last 2 months)
    last2 = meses_sorted[-2:]
    daily_dates  = []
    daily_labels = []
    daily_ventas = []
    daily_costo  = []
    for d in sorted(daily.keys()):
        if d[:7] in last2:
            daily_dates.append(d)
            d_dt = datetime.strptime(d, '%Y-%m-%d')
            daily_labels.append(f"{d_dt.day:02d} {MESES_ES[d_dt.month]}")
            daily_ventas.append(round(daily[d]['ventas']))
            daily_costo.append(round(daily[d]['costo']))

    # Productos por mes (last 2)
    prods_por_mes_js = {}
    for m in last2:
        prods = monthly[m]['productos']
        arr = []
        for nombre, data in sorted(prods.items(), key=lambda x: -x[1]['ventas']):
            arr.append({
                'nombre': nombre,
                'ventas': round(data['ventas']),
                'costo':  round(data['costo']),
                'qty':    round(data['qty'])
            })
        prods_por_mes_js[m] = arr

    # totalVentasPorMes
    total_v_por_mes = {m: round(monthly[m]['ventas']) for m in last2}

    mes_activo = last2[-1] if last2 else meses_sorted[-1]

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    js = f"""
// ═══════════════════════════════════════════════════════
// AUTO-GENERADO por actualizar.py — {now}
// ═══════════════════════════════════════════════════════

var allDailyDates  = {json.dumps(daily_dates)};
var allDailyLabels = {json.dumps(daily_labels)};
var allDailyVentas = {json.dumps(daily_ventas)};
var allDailyCosto  = {json.dumps(daily_costo)};

var meses          = {json.dumps(labels)};
var mensualVentas  = {json.dumps(ventas_m)};
var mensualCosto   = {json.dumps(costo_m)};
var mensualUB      = mensualVentas.map(function(v,i){{ return v - mensualCosto[i]; }});
var mensualMargen  = mensualVentas.map(function(v,i){{ return v>0?((v-mensualCosto[i])/v*100).toFixed(1):'0'; }});
var mensualGastos  = {json.dumps(gastos_m)};
var mensualCompras = mensualCosto.slice();  // Aproximación: compras ≈ costo ventas

var mesActivo = '{mes_activo}';

var totalVentasPorMes = {json.dumps(total_v_por_mes)};

var productosPorMes = {json.dumps(prods_por_mes_js, ensure_ascii=False, indent=2)};

var gastosPorMes = {{}};
"""

    # Gastos por mes
    for m, g_list in gastos_ext.items():
        if m in meses_sorted and g_list:
            js += f"gastosPorMes['{m}'] = {json.dumps(g_list, ensure_ascii=False)};\n"

    js += f"""
function getProductosForMes(mes) {{
  return productosPorMes[mes] || productosPorMes['{mes_activo}'] || [];
}}
function getGastosForMes(mes) {{
  return gastosPorMes[mes] || [];
}}

// Flujo caja y compras (placeholder — agrega en gastos.json si tienes datos)
var mensualCompras = mensualCosto.slice();
var cajaData = {{
  entradas: mensualVentas.map(function(v){{ return Math.round(v*0.06); }}),
  salidas:  mensualVentas.map(function(v){{ return Math.round(v*0.35); }}),
  neto:     mensualUB
}};
var totalCxP = 0;

function getDonutForMes(mes) {{
  var prods = getProductosForMes(mes);
  var total = prods.reduce(function(s,p){{return s+p.costo;}},0);
  return {{mat: Math.round(total*0.79), otros: Math.round(total*0.21), total: total}};
}}
"""
    return js

# ── 5. Inyectar datos en el template ──────────────────────────
def inject_data(js_data):
    if not os.path.exists(TEMPLATE):
        print(f"ERROR: No se encontró el template: {TEMPLATE}")
        print("       Asegúrate de que bloquera-funez-template.html esté en la carpeta.")
        input("\nPresiona ENTER para cerrar...")
        sys.exit(1)

    with open(TEMPLATE, 'r', encoding='utf-8') as f:
        html = f.read()

    # Reemplaza el bloque de datos entre marcadores
    marker_start = '// ══ DATOS REALES'
    marker_end   = '// ══ PRO ENHANCEMENTS'

    start_idx = html.find(marker_start)
    end_idx   = html.find(marker_end)

    if start_idx == -1 or end_idx == -1:
        print("ADVERTENCIA: No se encontraron marcadores en el template.")
        print("             Copiando template sin modificar datos...")
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            f.write(html)
        return

    new_html = html[:start_idx] + js_data + "\n" + html[end_idx:]
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f"✓ Dashboard actualizado: {OUTPUT}")

# ── 6. Cargar gastos manuales ──────────────────────────────────
def load_gastos():
    if not os.path.exists(GASTOS_FILE):
        return {}
    with open(GASTOS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# ── MAIN ───────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Bloquera Fúnez — Actualizador de Dashboard")
    print("=" * 55)

    aks_path = find_aks()

    print("⏳ Leyendo archivo .aks ...")
    with open(aks_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    print("⏳ Procesando ventas ...")
    ventas          = parse_inserts(lines, 'venta')
    venta_productos = parse_inserts(lines, 'venta_producto')
    print(f"   → {len(ventas):,} ventas | {len(venta_productos):,} líneas de producto")

    print("⏳ Agregando datos mensuales ...")
    monthly, daily = build_monthly(ventas, venta_productos)

    meses_encontrados = sorted(monthly.keys())
    print(f"   → Meses con datos: {', '.join(meses_encontrados)}")

    gastos_ext = load_gastos()
    if gastos_ext:
        print(f"   → Gastos cargados desde gastos.json")

    print("⏳ Generando dashboard ...")
    js_data = build_js(monthly, daily, gastos_ext)
    inject_data(js_data)

    total_ventas = sum(monthly[m]['ventas'] for m in meses_encontrados)
    print(f"\n{'─'*55}")
    print(f"  ✅ Dashboard listo!")
    print(f"  📊 Total ventas procesadas: C$ {total_ventas:,.0f}")
    print(f"  📅 Período: {meses_encontrados[0]} → {meses_encontrados[-1]}")
    print(f"{'─'*55}")

    resp = input("\n¿Abrir el dashboard ahora? (S/n): ").strip().lower()
    if resp != 'n':
        webbrowser.open(f"file:///{OUTPUT.replace(chr(92), '/')}")
        print("✓ Abriendo en el navegador...")

    input("\nPresiona ENTER para cerrar...")

if __name__ == '__main__':
    main()
