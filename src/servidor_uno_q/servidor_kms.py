from flask import Flask, render_template_string, jsonify, request
import paho.mqtt.client as mqtt
import threading
import uuid

app = Flask(__name__)

estado_seguridad = {
    "admin1_ok": False,
    "admin2_ok": False,
    "token_sesion": None,
    "ultima_llave_fisica": None
}

boveda_archivos = {
    "proyecto_final.pdf.enc": "GESTO_DERECHA",
    "base_datos.sql.enc": "GESTO_AGITAR"
}

def on_connect(client, userdata, flags, rc):
    print("[✓] KMS Conectado al Broker MQTT")
    client.subscribe("boveda/acceso")
    client.subscribe("boveda/llaves")

def on_message(client, userdata, msg):
    tema = msg.topic
    payload = msg.payload.decode()
    if tema == "boveda/acceso":
        estado_seguridad["admin1_ok"] = True
        estado_seguridad["token_sesion"] = payload
    elif tema == "boveda/llaves":
        estado_seguridad["ultima_llave_fisica"] = payload

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
# Cambiar 'localhost' por 'mqtt_broker' si decides usar Docker
mqtt_client.connect("localhost", 1883, 60) 

hilo_mqtt = threading.Thread(target=mqtt_client.loop_forever)
hilo_mqtt.daemon = True
hilo_mqtt.start()

HTML_MAIN = """
<!DOCTYPE html><html><head><title>Bóveda KMS</title>
<style>body{background:#0d1117; color:#0f0; font-family:monospace; padding:30px; text-align:center;}
.box{border:2px solid #0f0; padding:20px; display:inline-block; background:#161b22;}
.archivo{border:1px solid #555; padding:15px; margin:10px; cursor:pointer; background:#21262d;}
button, input, select{background:#238636; color:white; padding:10px; cursor:pointer;}
</style></head><body>
<h1>SISTEMA K.M.S. ZERO TRUST</h1><div id="pantalla" class="box">Cargando...</div>
<script>
let archivo_actual = null;
function renderizarDashboard() {
    fetch('/api/archivos').then(r=>r.json()).then(data => {
        let html = "<h2>BÓVEDA DESBLOQUEADA</h2><hr>";
        for(let [archivo, gesto] of Object.entries(data)) {
            html += `<div class="archivo" onclick="prepararDesbloqueo('${archivo}')">🔒 ${archivo}</div>`;
        }
        html += `<hr><input type="text" id="nn" placeholder="archivo.txt"><select id="ng">
        <option value="GESTO_AGITAR">Agitar</option><option value="GESTO_VOLTEAR">Voltear</option>
        <option value="GESTO_DERECHA">Derecha</option><option value="GESTO_IZQUIERDA">Izquierda</option>
        </select><button onclick="cifrar()">CIFRAR NUEVO</button>`;
        document.getElementById('pantalla').innerHTML = html;
    });
}
function cifrar() {
    fetch('/api/cifrar', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({nombre: document.getElementById('nn').value, gesto: document.getElementById('ng').value})
    }).then(()=>renderizarDashboard());
}
function prepararDesbloqueo(archivo) {
    archivo_actual = archivo; fetch('/api/reset_llave');
    document.getElementById('pantalla').innerHTML = `<h3 style='color:orange'>ESPERANDO LLAVE FÍSICA PARA: ${archivo}</h3><button onclick="renderizarDashboard()">Volver</button>`;
}
setInterval(() => {
    fetch('/api/estado').then(r=>r.json()).then(st => {
        let p = document.getElementById('pantalla');
        if (!st.admin1_ok) { p.innerHTML = "<h2 style='color:red'>ACCESO DENEGADO</h2><p>Inserte Token Físico.</p>"; archivo_actual = null; } 
        else if (st.admin1_ok && !st.admin2_ok) { p.innerHTML = `<h2 style='color:yellow'>TOKEN DETECTADO: ${st.token_sesion}</h2><p>Esperando Admin 2...</p>`; } 
        else if (st.admin1_ok && st.admin2_ok) {
            if (archivo_actual == null && p.innerHTML.includes("TOKEN")) renderizarDashboard();
            else if (archivo_actual != null) {
                fetch('/api/check_desbloqueo/' + archivo_actual).then(r=>r.json()).then(res => {
                    if(res.status == "exito") p.innerHTML = `<h2 style='color:cyan'>[✓] ACCESO CONCEDIDO A ${archivo_actual}</h2><button onclick="archivo_actual=null; renderizarDashboard()">Cerrar</button>`;
                    else if(res.status == "error") p.innerHTML = `<h2 style='color:red'>[X] FALLO FÍSICO</h2><button onclick="archivo_actual=null; renderizarDashboard()">Volver</button>`;
                });
            }
        }
    });
}, 1000);
</script></body></html>
"""

HTML_MOBILE = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{background:#222; color:white; text-align:center; padding:20px; font-family:sans-serif;}
.btn{background:#28a745; color:white; padding:20px; font-size:20px; width:100%;}</style></head>
<body><h2>ADMIN 2</h2><div id="info">Buscando solicitudes...</div>
<script>
setInterval(() => {
    fetch('/api/estado').then(r=>r.json()).then(st => {
        if(st.admin1_ok && !st.admin2_ok) {
            document.getElementById('info').innerHTML = `<p>Token: ${st.token_sesion}</p><button class="btn" onclick="fetch('/api/autorizar')">APROBAR ACCESO</button>`;
        } else if (st.admin1_ok && st.admin2_ok) { document.getElementById('info').innerHTML = "<h3 style='color:green'>BÓVEDA ACTIVA</h3>"; }
    });
}, 1000);
</script></body></html>
"""

@app.route('/')
def index(): return render_template_string(HTML_MAIN)
@app.route('/admin-remoto')
def admin_remoto(): return render_template_string(HTML_MOBILE)
@app.route('/api/estado')
def api_estado(): return jsonify(estado_seguridad)
@app.route('/api/autorizar')
def api_autorizar(): 
    if estado_seguridad["admin1_ok"]: estado_seguridad["admin2_ok"] = True
    return jsonify({"msg": "ok"})
@app.route('/api/archivos')
def api_archivos(): return jsonify(boveda_archivos)
@app.route('/api/cifrar', methods=['POST'])
def api_cifrar(): 
    boveda_archivos[request.json['nombre'] + ".enc"] = request.json['gesto']
    return jsonify({"msg": "ok"})
@app.route('/api/reset_llave')
def reset_llave(): 
    estado_seguridad["ultima_llave_fisica"] = None
    return jsonify({"msg": "ok"})
@app.route('/api/check_desbloqueo/<archivo>')
def check_desbloqueo(archivo):
    req = boveda_archivos.get(archivo)
    rec = estado_seguridad["ultima_llave_fisica"]
    if rec is None: return jsonify({"status": "esperando"})
    elif rec == req: return jsonify({"status": "exito"})
    else: 
        estado_seguridad["ultima_llave_fisica"] = None
        return jsonify({"status": "error"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)