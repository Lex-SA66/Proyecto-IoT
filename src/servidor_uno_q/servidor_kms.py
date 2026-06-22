# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for, send_file
import paho.mqtt.client as mqtt
from cryptography.fernet import Fernet
import os
import json
import io

app = Flask(__name__)
app.secret_key = "super_secreto_escom"

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

CARPETA_UPLOADS = "boveda_archivos_cifrados"
if not os.path.exists(CARPETA_UPLOADS): os.makedirs(CARPETA_UPLOADS)

ARCHIVO_LLAVE = "llave_maestra.key"
ARCHIVO_BD = "boveda_db.json"
ARCHIVO_USUARIOS = "usuarios_db.json"

if os.path.exists(ARCHIVO_LLAVE):
    with open(ARCHIVO_LLAVE, "rb") as f: LLAVE_AES = f.read()
else:
    LLAVE_AES = Fernet.generate_key()
    with open(ARCHIVO_LLAVE, "wb") as f: f.write(LLAVE_AES)
cifrador = Fernet(LLAVE_AES)

def cargar_json(ruta):
    if os.path.exists(ruta):
        with open(ruta, "r") as f: return json.load(f)
    return {}

def guardar_json(ruta, datos):
    with open(ruta, "w") as f: json.dump(datos, f)

boveda_archivos = cargar_json(ARCHIVO_BD)
usuarios_db = cargar_json(ARCHIVO_USUARIOS)

if not usuarios_db:
    usuarios_db = {"alexandra": {"pwd": "escom2026", "estado": "aprobado"}}
    guardar_json(ARCHIVO_USUARIOS, usuarios_db)

operacion = {
    "activa": False, "usuario": None, "accion": None, "archivo": None,
    "gesto_requerido": None, "gesto_recibido": None, "nombre_original": None,
    "hardware_ok": False, "admin_aprobado": False, "ID_descarga_lista": None, "resultado_final": None,
    "archivo_bytes_crudos": None
}

def on_connect(client, userdata, flags, rc):
    print("[V] Servidor KMS activo en puerto 1883. Escuchando canal MQTT...")
    client.subscribe("boveda/llaves")
    client.subscribe("boveda/acceso")

def on_message(client, userdata, msg):
    tema = msg.topic
    payload = msg.payload.decode('utf-8', errors='ignore').replace('\x00', '').strip()
    
    print(">> [MQTT] Tema: " + tema + " | Recibido: [" + payload + "] | Solicitado: [" + str(operacion["gesto_requerido"]) + "]")
    
    if operacion["activa"] and not operacion["hardware_ok"]:
        if tema == "boveda/llaves":
            operacion["gesto_recibido"] = payload
            if payload == str(operacion["gesto_requerido"]).strip(): 
                operacion["hardware_ok"] = True
                print(">> [EXITO] Firma de Hardware validada correctamente.")
            else:
                print(">> [ERROR] El gesto no coincide. Operacion denegada.")

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect("127.0.0.1", 1883, 60)
mqtt_client.loop_start()

ESTILOS_CSS = """
<style>
    :root { --bg-deep: #06090f; --bg-surface: #0d1117; --bg-card: #161b22; --border-cyan: #38bdf8; --border-muted: #30363d; --text-pure: #f0f6fc; --text-gray: #8b949e; --neon-green: #4ade80; --neon-cyan: #0ea5e9; --neon-amber: #f59e0b; --neon-red: #f87171; }
    body { background: var(--bg-deep); color: var(--text-pure); font-family: monospace; padding: 40px 20px; margin: 0; }
    .wrapper { max-width: 900px; margin: 0 auto; }
    .header-logo { text-align: center; font-weight: 800; letter-spacing: 4px; color: var(--neon-cyan); margin-bottom: 30px; font-size: 26px; }
    .panel { background: var(--bg-surface); border: 1px solid var(--border-muted); border-radius: 16px; padding: 35px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); }
    .grid-vault { display: grid; grid-template-columns: 1fr; gap: 15px; margin-top: 20px; }
    .file-card { background: var(--bg-card); border: 1px solid var(--border-muted); padding: 18px 25px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; transition: all 0.25s ease; }
    .file-card:hover { border-color: var(--border-cyan); }
    .file-info b { color: var(--text-pure); font-size: 15px; }
    .file-info p { margin: 4px 0 0 0; font-size: 12px; color: var(--text-gray); }
    .btn { font-family: inherit; font-weight: 600; font-size: 13px; padding: 10px 20px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; transition: all 0.2s; }
    .btn-outline { background: transparent; border-color: var(--border-cyan); color: var(--border-cyan); }
    .btn-danger { background: rgba(248,113,113,0.1); border-color: rgba(248,113,113,0.3); color: var(--neon-red); text-decoration:none; display:inline-block; }
    .btn-go { background: var(--neon-green); color: #050505; font-weight: bold; width: 100%; padding: 14px; font-size: 14px; margin-top: 10px; }
    .input-field { background: var(--bg-deep); border: 1px solid var(--border-muted); color: #fff; padding: 14px; border-radius: 8px; width: 100%; box-sizing: border-box; margin-bottom: 12px; font-size: 14px; }
    .dropzone { border: 2px dashed #444; background: rgba(255,255,255,0.01); padding: 30px; text-align: center; border-radius: 10px; cursor: pointer; color: var(--neon-cyan); font-weight: 600; margin-bottom: 15px; display: block;}
    .badge-status { background: rgba(245,158,11,0.08); border: 1px dashed var(--neon-amber); color: var(--neon-amber); padding: 20px; border-radius: 10px; text-align: center; font-size: 14px; }
    .pulse { animation: alertPulse 1s infinite alternate; }
    @keyframes alertPulse { from { opacity: 0.7; transform: scale(0.99); } to { opacity: 1; transform: scale(1); } }
</style>
"""

HTML_BASE = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>KMS Zero Trust - ESCOM</title>" + ESTILOS_CSS + "</head><body>"

LOGIN_UI = HTML_BASE + """
<div class="wrapper">
    <div class="header-logo">Zero-Trust Authentication</div>
    <div class="panel" style="max-width: 480px; margin: 0 auto;">
        <h3 style="margin-top:0; color: var(--neon-cyan); border-bottom: 1px solid var(--border-muted); padding-bottom: 10px;">ACCESO AUTORIZADO (IAM)</h3>
        <form action="/login" method="POST">
            <input type="text" name="usr" class="input-field" placeholder="Identificador de Operador" required autocomplete="off">
            <input type="password" name="pwd" class="input-field" placeholder="Clave de Entrada" required autocomplete="off">
            <button type="submit" class="btn btn-go">VALIDAR IDENTIDAD</button>
        </form>
        <div style="margin-top:30px; border-top:1px dashed var(--border-muted); padding-top:20px;">
            <h4 style="margin:0 0 10px 0; color:var(--text-gray);">REGISTRAR NUEVA CREDENCIAL?</h4>
            <form action="/registro" method="POST">
                <input type="text" name="nuevo_usr" class="input-field" placeholder="Asignar Nuevo Usuario" required autocomplete="off">
                <input type="password" name="nuevo_pwd" class="input-field" placeholder="Asignar Contrasena" required autocomplete="off">
                <button type="submit" class="btn" style="width:100%; background:#21262d; color:#fff; border:1px solid var(--border-muted);">SOLICITAR ALTA</button>
            </form>
        </div>
    </div>
</div></body></html>
"""

USER_UI = HTML_BASE + """
<div class="wrapper">
    <div class="header-logo">KMS CORE VAULT OPERATOR</div>
    <div class="panel">
        <h2 style="margin:0 0 20px 0;">OPERADOR: <span style="color:var(--neon-green);">{{ usuario }}</span> <a href="/logout" class="btn btn-danger" style="float:right; padding:6px 12px; font-size:11px;">CERRAR SESION</a></h2>
        <div id="pantalla_central">Sincronizando sistemas criptograficos...</div>
    </div>
</div>
<script>
function ejecutar(accion, archivo) {
    fetch('/api/solicitar', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({accion: accion, archivo: archivo}) });
}

let panel_actual = "";

setInterval(() => {
    fetch('/api/estado').then(r=>r.json()).then(st => {
        let p = document.getElementById('pantalla_central');
        
        if(!st.activa) {
            if (panel_actual !== "idle") {
                panel_actual = "idle";
                let html = "<h3 style='color:var(--neon-cyan);'>Archivos Firmados Secundarios:</h3><div class='grid-vault'>";
                
                fetch('/api/archivos').then(r=>r.json()).then(data => {
                    if(Object.keys(data).length === 0) { html += "<p style='color:var(--text-gray); padding:10px;'>Boveda local vacia. Ningun binario inyectado.</p>"; }
                    for(let arch in data) {
                        html += `<div class="file-card">
                                    <div class="file-info"><b> ${data[arch].nombre_original}</b><p>LOCK_KEY: ${data[arch].gesto}</p></div>
                                    <div>
                                        <button class="btn btn-outline" onclick="ejecutar('DESCIFRAR', '${arch}')">Descifrar</button>
                                        <button class="btn btn-danger" onclick="ejecutar('ELIMINAR', '${arch}')">X</button>
                                    </div>
                                 </div>`;
                    }
                    html += `</div><hr style="border:1px solid var(--border-muted); margin:30px 0;">
                            <h3 style='color:var(--neon-cyan);'>INYECTAR FORMATO BINARIO A LA ARDUINO UNO Q</h3>
                            <form action="/api/subir_y_cifrar" method="POST" enctype="multipart/form-data">
                                <label class="dropzone">
                                    <input type="file" name="file_payload" style="display:none;" onchange="document.getElementById('lbl_file').innerText = 'Listo: ' + this.files[0].name" required>
                                    <span id="lbl_file">Haz click para cargar cualquier archivo (PDF, Imagen, ZIP, etc.)</span>
                                </label>
                                <select name="gesto_llave" class="input-field">
                                    <option value="GESTO_AGITAR">Cerrar con Gesto: Agitar Token</option>
                                    <option value="GESTO_VOLTEAR">Cerrar con Gesto: Voltear Token</option>
                                    <option value="GESTO_DERECHA">Cerrar con Gesto: Inclinar Derecha</option>
                                    <option value="GESTO_IZQUIERDA">Cerrar con Gesto: Inclinar Izquierda</option>
                                </select>
                                <button type="submit" class="btn btn-go">SOLICITAR PROTOCOLO DE CIFRADO</button>
                            </form>`;
                    p.innerHTML = html;
                });
            }
        } else if(st.activa && !st.hardware_ok) {
            if (panel_actual !== "hardware") {
                panel_actual = "hardware";
                p.innerHTML = `<div class="badge-status pulse"><h3 style="color:var(--neon-amber); margin-top:0;">REQUISITO PERIMETRAL DETECTADO</h3><p>Operacion: <b style="color:var(--neon-green);">${st.accion}</b> | Objetivo: <b>${st.nombre_original}</b></p><br><p style="font-size:16px; font-weight:bold; color:#fff; background:#222; padding:15px; border-radius:6px;">REALIZA EL GESTO EN LA ARDUINO: <span style="color:var(--neon-cyan);">${st.gesto_requerido}</span></p></div>`;
            }
        } else if(st.hardware_ok && !st.admin_aprobado) {
            if (panel_actual !== "admin") {
                panel_actual = "admin";
                p.innerHTML = `<div class="badge-status" style="border-color:var(--neon-cyan); color:var(--neon-cyan);"><h3 class="pulse">ESPERANDO AUTORIZACION REMOTA</h3><p>Firma fisica validada. Esperando a que el Administrador apruebe desde el panel movil.</p></div>`;
            }
        } else if(st.admin_aprobado && st.ID_descarga_lista) {
            if (panel_actual !== "completado") {
                panel_actual = "completado";
                if(st.accion === 'DESCIFRAR') {
                    p.innerHTML = `<div style="text-align:center; padding:20px;"><h3 style="color:var(--neon-green); font-size:22px; margin-top:0;">CANAL DESBLOQUEADO</h3><p style="color:var(--text-gray);">El archivo binario fue descifrado de forma segura en la RAM del servidor.</p><br><a href="/api/descargar_resultado" target="_blank"><button class="btn btn-go" style="max-width:350px; font-size:16px; padding:18px;">VISUALIZAR / ABRIR ARCHIVO</button></a><br><br><button class="btn btn-danger" onclick="fetch('/api/reset')" style="margin-top:15px;">CERRAR BUFFER DE MEMORIA RAM</button></div>`;
                } else {
                    p.innerHTML = `<div style="text-align:center; padding:20px;"><h3 style="color:var(--neon-green); font-size:22px; margin-top:0;">EXITO EN LA GESTION</h3><p>${st.resultado_final}</p><br><button class="btn btn-go" onclick="fetch('/api/reset')" style="max-width:250px;">VOLVER AL MENU</button></div>`;
                }
            }
        }
    });
}, 1000);
</script></body></html>
"""

ADMIN_UI = HTML_BASE + """
<div class="wrapper">
    <div class="header-logo" style="color:var(--neon-red);">CENTRO DE AUDITORIA REMOTA</div>
    <div class="panel">
        <h3 style="margin-top:0; color:var(--neon-red); border-bottom:1px solid var(--border-muted); padding-bottom:10px;">MONITOREO DE ACTIVIDAD CRYPT-CORE</h3>
        <div id="admin_log" style="background:var(--bg-deep); padding:20px; border-radius:10px; border:1px solid var(--border-muted);">Monitoreando...</div>
        <hr style="border:1px solid var(--border-muted); margin:30px 0;">
        <h3 style="color:var(--neon-cyan);">GESTION DE CREDENCIALES EN COLA (IAM)</h3>
        <div id="lista_usuarios">Escaneando solicitudes entrantes...</div>
    </div>
</div>
<script>
setInterval(() => {
    fetch('/api/estado').then(r=>r.json()).then(st => {
        let log = document.getElementById('admin_log');
        if(!st.activa) { 
            log.innerHTML = "<span style='color:var(--text-gray);'>[SISTEMA EN REPOSO] Ninguna solicitud de desencriptado activa.</span>"; 
        } else {
            let hw_status = st.hardware_ok ? "<span style='color:var(--neon-green); font-weight:bold;'>[FISICA ACEPTADA]</span>" : "<span class='pulse' style='color:var(--neon-amber);'>[ESPERANDO HARDWARE...]</span>";
            let color_btn = st.accion === 'ELIMINAR' ? 'var(--neon-red)' : (st.accion === 'CIFRAR' ? 'var(--neon-green)' : 'var(--neon-cyan)');
            
            let action_btn = "";
            if (st.hardware_ok && !st.admin_aprobado) {
                action_btn = `<div style="margin-top:25px; padding: 25px; border: 2px dashed var(--neon-cyan); background: rgba(14,165,233,0.1); text-align: center; border-radius: 12px;">
                    <h2 style="color:var(--neon-cyan); margin-top:0;" class="pulse">ALERTA TACTICA: REQUIERE TU FIRMA</h2>
                    <button class="btn btn-go" onclick="fetch('/api/aprobar')" style="background:${color_btn}; color:#000; font-size: 18px; padding: 15px;">APROBAR TRANSACCION: ${st.accion}</button>
                    <button class="btn btn-danger" onclick="fetch('/api/reset')" style="width:100%; margin-top:10px; background:#222; color:#fff; border-color:#444;">ABORTAR PETICION Y BLOQUEAR</button>
                </div>`;
            } else if (st.admin_aprobado) {
                action_btn = `<div style="margin-top:25px; padding: 20px; border: 1px dashed var(--neon-green); background: rgba(74,222,128,0.1); text-align: center; border-radius: 12px;">
                    <h3 style="color:var(--neon-green); margin:0;">ACCION APROBADA EXITOSAMENTE</h3>
                    <p style="color:var(--text-gray); margin-top:5px;">El operador ya puede continuar desde su panel.</p>
                </div>`;
            }
            
            log.innerHTML = `<div>
                <p><b>Usuario Operador:</b> <span style="color:var(--neon-cyan);">${st.usuario}</span></p>
                <p><b>Accion Critica:</b> <span style="color:${color_btn}; font-weight:bold;">${st.accion}</span></p>
                <p><b>Binario Solicitado:</b> ${st.nombre_original}</p>
                <p><b>Validacion Biometrica/Gesto:</b> ${hw_status}</p>
            </div>${action_btn}`;
        }
    });
    fetch('/api/pendientes').then(r=>r.json()).then(usrs => {
        let div = document.getElementById('lista_usuarios');
        if(usrs.length === 0) { div.innerHTML = "<p style='color:var(--text-gray); font-size:13px;'>No hay peticiones de alta en espera de firma.</p>"; }
        else {
            let buffer = "";
            usrs.forEach(u => {
                buffer += `<div class="file-card">
                    <b>ID_OPERADOR: ${u}</b>
                    <div>
                        <button class="btn" style="background:var(--neon-green); color:#000; padding:6px 12px; font-weight:bold;" onclick="fetch('/api/gestionar_usr', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({usr:'${u}', accion:'aprobar'})})">Aprobar Alta</button>
                        <button class="btn btn-danger" style="padding:6px 12px;" onclick="fetch('/api/gestionar_usr', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({usr:'${u}', accion:'rechazar'})})">Denegar</button>
                    </div></div>`;
            });
            div.innerHTML = buffer;
        }
    });
}, 1000);
</script></body></html>
"""

@app.route('/')
def index():
    if 'usuario' not in session: return render_template_string(LOGIN_UI)
    return render_template_string(USER_UI, usuario=session['usuario'].upper())

@app.route('/admin')
def admin_panel():
    return render_template_string(ADMIN_UI)

@app.route('/login', methods=['POST'])
def login():
    session.clear()
    usr = request.form['usr'].lower()
    pwd = request.form['pwd']
    if usr in usuarios_db and usuarios_db[usr]["pwd"] == pwd:
        if usuarios_db[usr]["estado"] == "aprobado":
            session['usuario'] = usr
            return redirect(url_for('index'))
        else: return "CUENTA BLOQUEADA/PENDIENTE DE AUTORIZACION ADMIN"
    return "CREDENCIALES INCORRECTAS"

@app.route('/registro', methods=['POST'])
def registro():
    usr = request.form['nuevo_usr'].lower()
    pwd = request.form['nuevo_pwd']
    if usr in usuarios_db: return "EL USUARIO YA EXISTE"
    usuarios_db[usr] = {"pwd": pwd, "estado": "pendiente"}
    guardar_json(ARCHIVO_USUARIOS, usuarios_db)
    return redirect(url_for('index'))

@app.route('/api/pendientes')
def api_pendientes(): return jsonify([usr for usr, datos in usuarios_db.items() if datos["estado"] == "pendiente"])

@app.route('/api/gestionar_usr', methods=['POST'])
def api_gestionar_usr():
    req = request.json
    if req['accion'] == 'aprobar': usuarios_db[req['usr']]["estado"] = "aprobado"
    elif req['accion'] == 'rechazar': del usuarios_db[req['usr']]
    guardar_json(ARCHIVO_USUARIOS, usuarios_db)
    return jsonify({"msg": "ok"})

@app.route('/api/archivos')
def api_archivos(): return jsonify(boveda_archivos)

@app.route('/api/estado')
def api_estado():
    estado_seguro = operacion.copy()
    if estado_seguro.get("archivo_bytes_crudos") is not None:
        estado_seguro["archivo_bytes_crudos"] = True
    return jsonify(estado_seguro)

@app.route('/api/subir_y_cifrar', methods=['POST'])
def api_subir_y_cifrar():
    if 'usuario' not in session: return redirect(url_for('index'))
    file = request.files['file_payload']
    gesto = request.form['gesto_llave']
    if file:
        operacion["activa"] = True
        operacion["usuario"] = session['usuario']
        operacion["accion"] = "CIFRAR"
        operacion["nombre_original"] = file.filename
        operacion["gesto_requerido"] = gesto
        operacion["archivo_bytes_crudos"] = file.read()
        operacion["hardware_ok"] = False
        operacion["admin_aprobado"] = False
        operacion["ID_descarga_lista"] = None
        operacion["resultado_final"] = None
    return redirect(url_for('index'))

@app.route('/api/solicitar', methods=['POST'])
def api_solicitar():
    req = request.json
    operacion["activa"] = True
    operacion["usuario"] = session['usuario']
    operacion["accion"] = req['accion']
    operacion["archivo"] = req['archivo']
    operacion["nombre_original"] = boveda_archivos[req['archivo']]["nombre_original"]
    operacion["gesto_requerido"] = boveda_archivos[req['archivo']]["gesto"]
    operacion["hardware_ok"] = False
    operacion["admin_aprobado"] = False
    return jsonify({"msg": "ok"})

@app.route('/api/aprobar')
def api_aprobar():
    if operacion["hardware_ok"] and not operacion["admin_aprobado"]:
        operacion["admin_aprobado"] = True
        archivo = operacion["archivo"]
        
        if operacion["accion"] == 'CIFRAR':
            archivo_id = "file_" + str(len(boveda_archivos) + 1) + ".enc"
            bytes_encriptados = cifrador.encrypt(operacion["archivo_bytes_crudos"])
            with open(os.path.join(CARPETA_UPLOADS, archivo_id), "wb") as f: 
                f.write(bytes_encriptados)
            boveda_archivos[archivo_id] = {"nombre_original": operacion["nombre_original"], "gesto": operacion["gesto_requerido"]}
            guardar_json(ARCHIVO_BD, boveda_archivos)
            operacion["resultado_final"] = "Archivo " + operacion["nombre_original"] + " cifrado y almacenado con exito."
            operacion["ID_descarga_lista"] = "READY"
            
        elif operacion["accion"] == 'DESCIFRAR':
            operacion["ID_descarga_lista"] = "READY"
            
        elif operacion["accion"] == 'ELIMINAR':
            ruta = os.path.join(CARPETA_UPLOADS, archivo)
            if os.path.exists(ruta): os.remove(ruta)
            del boveda_archivos[archivo]
            guardar_json(ARCHIVO_BD, boveda_archivos)
            operacion["resultado_final"] = "Archivo purgado del disco duro de forma permanente."
            operacion["ID_descarga_lista"] = "READY"
            
    return jsonify({"msg": "ok"})

@app.route('/api/descargar_resultado')
def api_descargar_resultado():
    if operacion["admin_aprobado"] and operacion["ID_descarga_lista"] and operacion["accion"] == 'DESCIFRAR':
        ruta_archivo = os.path.join(CARPETA_UPLOADS, operacion["archivo"])
        with open(ruta_archivo, "rb") as f: datos_cifrados = f.read()
        bytes_claros = cifrador.decrypt(datos_cifrados)
        return send_file(io.BytesIO(bytes_claros), download_name=operacion["nombre_original"], as_attachment=False)
    return "No autorizado", 403

@app.route('/api/reset')
def api_reset():
    for key in operacion: operacion[key] = False if type(operacion[key]) == bool else None
    return jsonify({"msg": "ok"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
