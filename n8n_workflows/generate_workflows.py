"""
Generador de workflows N8N para La Falla DF.
Produce 5 archivos JSON listos para importar o publicar via API.

Uso:
    python generate_workflows.py          # Genera los 5 JSON localmente
    python generate_workflows.py --push   # Borra workflows existentes y publica nuevos

Variables de entorno requeridas para --push:
    N8N_HOST    = URL de N8N (sin trailing slash)
    N8N_API_KEY = API Key de N8N
"""

import json
import os
import sys

# ─── Helpers base ─────────────────────────────────────────────────────────────

def node(id_, name, type_, version, x, y, params):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": version,
        "position": [x, y],
        "parameters": params,
    }

def sticky(id_, x, y, content, color=4, w=420, h=220):
    return node(id_, "📋 Credenciales", "n8n-nodes-base.stickyNote", 1, x, y, {
        "color": color, "width": w, "height": h, "content": content
    })

def build_connections(pairs):
    conns = {}
    for src, dst, src_out, dst_in in pairs:
        if src not in conns:
            conns[src] = {"main": []}
        while len(conns[src]["main"]) <= src_out:
            conns[src]["main"].append([])
        conns[src]["main"][src_out].append({"node": dst, "type": "main", "index": dst_in})
    return conns

def workflow(name, nodes, connections, tz="America/Bogota"):
    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": tz},
    }

def hdrs(*pairs):
    return {
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": k, "value": v} for k, v in pairs]},
    }

def jbody(js_fields):
    return {
        "sendBody": True,
        "contentType": "json",
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({" + js_fields + "}) }}",
    }

# ─── Constantes de headers ────────────────────────────────────────────────────

FASTAPI_HDRS   = hdrs(("X-API-Key", "={{$env.FASTAPI_API_KEY}}"))
CHATWOOT_HDRS  = hdrs(("api_access_token", "={{$env.CHATWOOT_API_TOKEN}}"))
OPENAI_HDRS    = hdrs(("Authorization", "=Bearer {{$env.OPENAI_API_KEY}}"))

# ─── Nombres de nodos ─────────────────────────────────────────────────────────

N_PARSE  = "🔍 Parsear Mensaje"
N_VCARD  = "🔧 Parsear + Combinar vCard"
N_CLS1   = "📊 Clasificar Contacto"
N_INS1   = "💾 Guardar Stakeholder"
N_LIPAR  = "🔧 Parsear LinkedIn"
N_CLS2   = "📊 Clasificar LinkedIn"
N_INS2   = "💾 Guardar Contacto LinkedIn"
N_VFY4   = "🔐 Verificar API Key"
N_TOP5   = "🏆 Top 5 Hot Leads"

# ─── Helpers de URL Chatwoot ──────────────────────────────────────────────────

def ct_conv_url(conv_id_js):
    """URL de mensajes para una conversación. conv_id_js es expresión JS (sin ={{ }})."""
    return "={{$env.CHATWOOT_API_BASE + '/conversations/' + " + conv_id_js + " + '/messages'}}"

CT_JUAN_URL      = ct_conv_url("$env.CHATWOOT_JUAN_CONVERSATION_ID")
CT_CONTACTS_URL  = "={{$env.CHATWOOT_API_BASE + '/contacts'}}"
CT_CONVS_URL     = "={{$env.CHATWOOT_API_BASE + '/conversations'}}"

# ─── Nota de credenciales ─────────────────────────────────────────────────────

CREDS_NOTE = """## Variables de entorno N8N (Settings → Environment)

- `FASTAPI_BASE_URL`              = URL FastAPI  (ej: http://api-stakeholders:8000)
- `FASTAPI_API_KEY`               = Clave compartida N8N ↔ FastAPI
- `CHATWOOT_API_BASE`             = URL base  (ej: https://chatwoot.host/api/v1/accounts/1)
- `CHATWOOT_API_TOKEN`            = Chatwoot → Settings → Access Token
- `CHATWOOT_WA_INBOX_ID`          = ID del inbox WhatsApp en Chatwoot
- `CHATWOOT_JUAN_CONVERSATION_ID` = ID conversación de Juan Carlos en Chatwoot
- `AUTHORIZED_WA_NUMBERS`         = Números autorizados (solo dígitos, separados por coma)
- `OPENAI_API_KEY`                = Token OpenAI

**WF1 — Configurar en Chatwoot:**
Settings → Integrations → Webhooks → URL:
`<N8N_HOST>/webhook/chatwoot-inbound-lafalla`
Eventos: ✅ Message Created"""

# ─── WF1: Alta Contacto WhatsApp ──────────────────────────────────────────────

def wf1():
    nodes = [
        sticky("s1", 240, 60, CREDS_NOTE, w=540, h=300),

        node("n_wh", "📱 Chatwoot Inbound Webhook", "n8n-nodes-base.webhook", 2, 240, 380, {
            "path": "chatwoot-inbound-lafalla",
            "httpMethod": "POST",
            "responseMode": "onReceived",
            "responseCode": 200,
        }),

        node("n_parse", N_PARSE, "n8n-nodes-base.code", 2, 480, 380, {
            "mode": "runOnceForEachItem",
            "jsCode": r"""
const body = $input.item.json.body ?? $input.item.json;

// Chatwoot dispara varios eventos — solo procesar mensajes entrantes
if (body.event !== 'message_created' || body.message_type !== 'incoming') {
  return { json: { skip: true, isAuthorized: false, intent: 'skip', conversationId: null } };
}

const senderPhone = (body.sender?.phone_number ?? '').replace(/\D/g, '');
const from = senderPhone;
const conversationId = body.conversation?.id ?? null;

const authList = (process.env.AUTHORIZED_WA_NUMBERS ?? '')
  .split(',').map(s => s.trim().replace(/\D/g, '')).filter(Boolean);
const isAuthorized = authList.length === 0 || authList.includes(from);

const rawText = (body.content ?? '').trim();
const isVCard = rawText.startsWith('BEGIN:VCARD');

let vCard = null;
if (isVCard) {
  const fnMatch    = rawText.match(/FN[^:]*:(.+)/);
  const telMatch   = rawText.match(/TEL[^:]*:(.+)/);
  const emailMatch = rawText.match(/EMAIL[^:]*:(.+)/);
  vCard = {
    nombre:   fnMatch?.[1]?.trim() ?? '',
    telefono: (telMatch?.[1]?.trim() ?? '').replace(/\D/g, ''),
    correo:   emailMatch?.[1]?.trim() ?? '',
  };
}

const txt = isVCard ? '' : rawText;
let intent = 'desconocido';
if (isVCard || /^\/contacto/i.test(txt)) intent = 'nuevo_contacto';
else if (/^\/enviado\s+\d+/i.test(txt))  intent = 'marcar_enviado';
else if (/^\/agregar/i.test(txt))         intent = 'agregar_linkedin';
else if (txt.length > 15)                intent = 'nuevo_contacto';

const matchId = txt.match(/\/enviado\s+(\d+)/i);

return { json: {
  from, isAuthorized, intent, rawText: txt, vCard, conversationId,
  descripcion: txt.replace(/^\/contacto\s*/i,'').replace(/^\/agregar\s*/i,'').trim(),
  enviado_id: matchId ? parseInt(matchId[1]) : null,
}};
""".strip()
        }),

        node("n_ifauth", "🔐 ¿Número Autorizado?", "n8n-nodes-base.if", 2, 720, 380, {
            "conditions": {
                "boolean": [{"value1": "={{$json.isAuthorized}}", "operation": "true"}]
            }
        }),

        node("n_sw", "🔀 Enrutar Intención", "n8n-nodes-base.switch", 3, 960, 280, {
            "mode": "rules",
            "rules": [
                {"conditions": {"string": [{"value1": "={{$json.intent}}", "operation": "equals", "value2": "nuevo_contacto"}]}},
                {"conditions": {"string": [{"value1": "={{$json.intent}}", "operation": "equals", "value2": "marcar_enviado"}]}},
                {"conditions": {"string": [{"value1": "={{$json.intent}}", "operation": "equals", "value2": "agregar_linkedin"}]}},
            ],
            "fallbackOutput": "extra",
        }),

        # ── Branch 0: nuevo_contacto ──────────────────────────────────────────

        node("n_oai1", "🤖 IA: Extraer Campos", "n8n-nodes-base.httpRequest", 4, 1200, 120, {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "none",
            **OPENAI_HDRS,
            **jbody(
                "model:'gpt-4o-mini',"
                "temperature:0.2,"
                "max_tokens:500,"
                "response_format:{type:'json_object'},"
                "messages:["
                  "{role:'system',content:'Eres asistente CRM de La Falla DF. "
                  "Extrae datos de contacto de mensajes en español. "
                  "Devuelve SOLO JSON válido con campos: nombre (string), rol (string), "
                  "correo (string), telefono (string, solo dígitos), "
                  "observaciones (descripción completa de quién es y por qué es relevante), "
                  "servicios (string), ubicacion (ciudad/región). "
                  "Campos no detectados = string vacío.'},"
                  "{role:'user',content:'Mensaje: '+$json.descripcion"
                  "+($json.vCard?'\\nvCard - Nombre: '+$json.vCard.nombre"
                  "+'  Tel: '+$json.vCard.telefono"
                  "+'  Email: '+$json.vCard.correo:'')}"
                "]"
            ),
        }),

        node("n_merge1", N_VCARD, "n8n-nodes-base.code", 2, 1440, 120, {
            "mode": "runOnceForEachItem",
            "jsCode": r"""
const aiContent = $input.item.json.choices?.[0]?.message?.content ?? '{}';
let contact = {};
try {
  const m = aiContent.match(/```json\n?([\s\S]*?)```/) ?? aiContent.match(/\{[\s\S]*\}/);
  contact = JSON.parse((m?.[1] ?? m?.[0] ?? aiContent).trim());
} catch(e) { contact = { observaciones: aiContent }; }

const vc = $('🔍 Parsear Mensaje').item.json.vCard;
if (vc) {
  if (vc.nombre && !contact.nombre)   contact.nombre = vc.nombre;
  if (vc.telefono && !contact.telefono) contact.telefono = vc.telefono;
  if (vc.correo && !contact.correo)   contact.correo = vc.correo;
}
return { json: {
  ...contact,
  fuente_archivo: 'WhatsApp Inbound',
  quien_contacta: $('🔍 Parsear Mensaje').item.json.from,
  _from: $('🔍 Parsear Mensaje').item.json.from,
  _conversationId: $('🔍 Parsear Mensaje').item.json.conversationId,
}};
""".strip()
        }),

        node("n_classify1", N_CLS1, "n8n-nodes-base.httpRequest", 4, 1680, 120, {
            "method": "POST",
            "url": "={{$env.FASTAPI_BASE_URL}}/classify",
            "authentication": "none",
            **FASTAPI_HDRS,
            **jbody(
                "nombre:$json.nombre||'',"
                "rol:$json.rol||'',"
                "correo:$json.correo||'',"
                "telefono:$json.telefono||'',"
                "observaciones:$json.observaciones||'',"
                "servicios:$json.servicios||'',"
                "ubicacion:$json.ubicacion||'',"
                "fuente_hojas:'WhatsApp Inbound'"
            ),
        }),

        node("n_insert1", N_INS1, "n8n-nodes-base.httpRequest", 4, 1920, 120, {
            "method": "POST",
            "url": "={{$env.FASTAPI_BASE_URL}}/stakeholders",
            "authentication": "none",
            **FASTAPI_HDRS,
            **jbody(
                f"nombre:$('{N_VCARD}').item.json.nombre||'',"
                f"rol:$('{N_VCARD}').item.json.rol||'',"
                f"correo:$('{N_VCARD}').item.json.correo||'',"
                f"telefono:$('{N_VCARD}').item.json.telefono||'',"
                f"observaciones:$('{N_VCARD}').item.json.observaciones||'',"
                f"servicios:$('{N_VCARD}').item.json.servicios||'',"
                f"ubicacion:$('{N_VCARD}').item.json.ubicacion||'',"
                "fuente_archivo:'WhatsApp Inbound',"
                f"quien_contacta:$('{N_VCARD}').item.json._from||''"
            ),
        }),

        node("n_wa_ok1", "✅ Confirmar Alta por WA", "n8n-nodes-base.httpRequest", 4, 2160, 120, {
            "method": "POST",
            "url": ct_conv_url(f"$('{N_VCARD}').item.json._conversationId"),
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                f"content:'✅ Guardado: *'+$('{N_INS1}').item.json.nombre+'*"
                f" → '+$('{N_CLS1}').item.json.clasificacion"
                f"+'\\n📌 '+$('{N_CLS1}').item.json.razon"
                f"+'\\n🆔 ID: '+($('{N_INS1}').item.json.id??'guardado'),"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        # ── Branch 1: marcar_enviado ──────────────────────────────────────────

        node("n_loglin", "📝 Registrar Enviado LinkedIn", "n8n-nodes-base.httpRequest", 4, 1200, 320, {
            "method": "POST",
            "url": "={{$env.FASTAPI_BASE_URL}}/interactions",
            "authentication": "none",
            **FASTAPI_HDRS,
            **jbody(
                "stakeholder_id:$json.enviado_id,"
                "campaign:'linkedin_clientes',"
                "canal:'linkedin',"
                "direccion:'out',"
                "mensaje:'Marcado por gerente',"
                "status:'sent'"
            ),
        }),

        node("n_wa_lin", "✅ Confirmar Registro LinkedIn", "n8n-nodes-base.httpRequest", 4, 1440, 320, {
            "method": "POST",
            "url": ct_conv_url(f"$('{N_PARSE}').item.json.conversationId"),
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                "content:'✅ LinkedIn registrado. ID '+$json.stakeholder_id+' no aparecerá en el próximo dashboard semanal.',"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        # ── Branch 2: agregar_linkedin ────────────────────────────────────────

        node("n_oai2", "🤖 IA: Extraer LinkedIn", "n8n-nodes-base.httpRequest", 4, 1200, 520, {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "none",
            **OPENAI_HDRS,
            **jbody(
                "model:'gpt-4o-mini',"
                "temperature:0.2,"
                "max_tokens:400,"
                "response_format:{type:'json_object'},"
                "messages:["
                  "{role:'system',content:'Extrae datos de contacto. "
                  "Devuelve JSON: {nombre, rol, correo, telefono, observaciones, servicios, ubicacion}. "
                  "Campos no detectados = string vacío.'},"
                  "{role:'user',content:$json.descripcion}"
                "]"
            ),
        }),

        node("n_merge2", N_LIPAR, "n8n-nodes-base.code", 2, 1440, 520, {
            "mode": "runOnceForEachItem",
            "jsCode": r"""
const ai = $input.item.json.choices?.[0]?.message?.content ?? '{}';
let c = {};
try { c = JSON.parse(ai.match(/\{[\s\S]*\}/)?.[0] ?? ai); } catch(e) { c = {observaciones: ai}; }
return { json: {
  ...c,
  fuente_archivo: 'LinkedIn Inbound',
  quien_contacta: $('🔍 Parsear Mensaje').item.json.from,
  _from: $('🔍 Parsear Mensaje').item.json.from,
  _conversationId: $('🔍 Parsear Mensaje').item.json.conversationId,
}};
""".strip()
        }),

        node("n_classify2", N_CLS2, "n8n-nodes-base.httpRequest", 4, 1680, 520, {
            "method": "POST",
            "url": "={{$env.FASTAPI_BASE_URL}}/classify",
            "authentication": "none",
            **FASTAPI_HDRS,
            **jbody(
                "nombre:$json.nombre||'',"
                "rol:$json.rol||'',"
                "observaciones:$json.observaciones||'',"
                "fuente_hojas:'LinkedIn Inbound'"
            ),
        }),

        node("n_insert2", N_INS2, "n8n-nodes-base.httpRequest", 4, 1920, 520, {
            "method": "POST",
            "url": "={{$env.FASTAPI_BASE_URL}}/stakeholders",
            "authentication": "none",
            **FASTAPI_HDRS,
            **jbody(
                f"nombre:$('{N_LIPAR}').item.json.nombre||'',"
                f"rol:$('{N_LIPAR}').item.json.rol||'',"
                f"correo:$('{N_LIPAR}').item.json.correo||'',"
                f"telefono:$('{N_LIPAR}').item.json.telefono||'',"
                f"observaciones:$('{N_LIPAR}').item.json.observaciones||'',"
                "fuente_archivo:'LinkedIn Inbound',"
                f"quien_contacta:$('{N_LIPAR}').item.json._from||''"
            ),
        }),

        node("n_wa_ok2", "✅ Confirmar LinkedIn", "n8n-nodes-base.httpRequest", 4, 2160, 520, {
            "method": "POST",
            "url": ct_conv_url(f"$('{N_LIPAR}').item.json._conversationId"),
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                f"content:'✅ Contacto de LinkedIn guardado: *'+$('{N_INS2}').item.json.nombre"
                f"+'* → '+$('{N_CLS2}').item.json.clasificacion,"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        # ── Fallback: comando desconocido ─────────────────────────────────────

        node("n_wa_help", "❓ Enviar Ayuda", "n8n-nodes-base.httpRequest", 4, 1200, 720, {
            "method": "POST",
            "url": ct_conv_url(f"$('{N_PARSE}').item.json.conversationId"),
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                "content:"
                "'🤖 *Bot CRM La Falla*\\n\\n"
                "Comandos disponibles:\\n\\n"
                "📇 *Envía una tarjeta de contacto* + descripción → Nueva alta automática\\n\\n"
                "`/contacto <descripción>` → Alta con texto libre\\n\\n"
                "`/enviado <ID>` → Marcar cliente como contactado en LinkedIn\\n\\n"
                "`/agregar <nombre, descripción>` → Agregar contacto desde LinkedIn',"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        node("n_noop", "🚫 No Autorizado", "n8n-nodes-base.noOp", 1, 960, 500, {}),
    ]

    pairs = [
        ("📱 Chatwoot Inbound Webhook",    N_PARSE,                           0, 0),
        (N_PARSE,                          "🔐 ¿Número Autorizado?",          0, 0),
        ("🔐 ¿Número Autorizado?",         "🔀 Enrutar Intención",            0, 0),
        ("🔐 ¿Número Autorizado?",         "🚫 No Autorizado",                1, 0),
        ("🔀 Enrutar Intención",           "🤖 IA: Extraer Campos",           0, 0),
        ("🔀 Enrutar Intención",           "📝 Registrar Enviado LinkedIn",   1, 0),
        ("🔀 Enrutar Intención",           "🤖 IA: Extraer LinkedIn",         2, 0),
        ("🔀 Enrutar Intención",           "❓ Enviar Ayuda",                 3, 0),
        ("🤖 IA: Extraer Campos",          N_VCARD,                           0, 0),
        (N_VCARD,                          N_CLS1,                            0, 0),
        (N_CLS1,                           N_INS1,                            0, 0),
        (N_INS1,                           "✅ Confirmar Alta por WA",        0, 0),
        ("📝 Registrar Enviado LinkedIn",  "✅ Confirmar Registro LinkedIn",  0, 0),
        ("🤖 IA: Extraer LinkedIn",        N_LIPAR,                           0, 0),
        (N_LIPAR,                          N_CLS2,                            0, 0),
        (N_CLS2,                           N_INS2,                            0, 0),
        (N_INS2,                           "✅ Confirmar LinkedIn",           0, 0),
    ]

    return workflow("La Falla | 01 - Alta Contacto WhatsApp", nodes, build_connections(pairs))


# ─── WF2: Outbound Mensual Proveedores ────────────────────────────────────────

def wf2():
    nodes = [
        sticky("s2", 240, 60,
            CREDS_NOTE + "\n\n**⚠️ Template HSM:**\n"
            "Registrar `locacion_mantenimiento_lafalla` en Meta Business Manager.\n"
            "Luego agregar en Chatwoot → Settings → Inboxes → WhatsApp → Message Templates.",
            w=540, h=340),

        node("n_sched", "🗓️ Primer Lunes del Mes 9AM", "n8n-nodes-base.scheduleTrigger", 1, 240, 400, {
            "rule": {"interval": [{"field": "cronExpression"}]},
            "cronExpression": "0 14 1-7 * 1",
        }),

        node("n_get", "📋 Obtener Proveedores", "n8n-nodes-base.httpRequest", 4, 480, 400, {
            "method": "GET",
            "url": "={{$env.FASTAPI_BASE_URL}}/stakeholders",
            "authentication": "none",
            **FASTAPI_HDRS,
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "clasificacion", "value": "Proveedores (Locaciones)"},
                {"name": "con_telefono",  "value": "true"},
            ]},
        }),

        node("n_filter", "🔧 Filtrar Cooldown 25 días", "n8n-nodes-base.code", 2, 720, 400, {
            "mode": "runOnceForAllItems",
            "jsCode": r"""
const items = $input.all();
const stakeholders = Array.isArray(items[0]?.json) ? items[0].json : items.map(i => i.json);
const now = Date.now();
const COOLDOWN_MS = 25 * 24 * 60 * 60 * 1000;

const toSend = stakeholders.filter(s => {
  const last = s.last_outbound_whatsapp ? new Date(s.last_outbound_whatsapp).getTime() : 0;
  return (now - last) > COOLDOWN_MS;
});

return toSend.map(s => ({
  json: {
    id: s.id,
    nombre: s.nombre ?? '',
    telefono: s.telefono ?? '',
    descripcion: s.servicios ?? s.observaciones ?? 'tu espacio',
  }
}));
""".strip()
        }),

        node("n_ifdata2", "❓ ¿Hay Proveedores?", "n8n-nodes-base.if", 2, 960, 400, {
            "conditions": {"number": [{"value1": "={{$input.all().length}}", "operation": "larger", "value2": 0}]}
        }),

        node("n_batch", "📦 Procesar de a 1", "n8n-nodes-base.splitInBatches", 3, 1200, 300, {
            "batchSize": 1, "options": {}
        }),

        node("n_create_ct", "➕ Crear Contacto Chatwoot", "n8n-nodes-base.httpRequest", 4, 1440, 300, {
            "method": "POST",
            "url": CT_CONTACTS_URL,
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                "name:$json.nombre,"
                "phone_number:'+'+$json.telefono"
            ),
        }),

        node("n_send_tmpl", "📤 Crear Conversación con Template", "n8n-nodes-base.httpRequest", 4, 1680, 300, {
            "method": "POST",
            "url": CT_CONVS_URL,
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                "inbox_id:Number($env.CHATWOOT_WA_INBOX_ID),"
                "contact_id:$json.id,"
                "message:{template_params:{"
                  "name:'locacion_mantenimiento_lafalla',"
                  "category:'UTILITY',"
                  "language:'es',"
                  "processed_params:{"
                    "'1':$('📦 Procesar de a 1').item.json.nombre,"
                    "'2':$('📦 Procesar de a 1').item.json.descripcion||'tu espacio'"
                  "}"
                "}}"
            ),
        }),

        node("n_log2", "📝 Registrar Envío", "n8n-nodes-base.httpRequest", 4, 1920, 300, {
            "method": "POST",
            "url": "={{$env.FASTAPI_BASE_URL}}/interactions",
            "authentication": "none",
            **FASTAPI_HDRS,
            **jbody(
                "stakeholder_id:$('📦 Procesar de a 1').item.json.id,"
                "campaign:'whatsapp_proveedores_mensual',"
                "canal:'whatsapp',"
                "direccion:'out',"
                "status:'sent'"
            ),
        }),

        node("n_summary_code", "📊 Contar Resultados", "n8n-nodes-base.code", 2, 2160, 300, {
            "mode": "runOnceForAllItems",
            "jsCode": r"""
const total = $input.all().length;
return [{ json: { total_enviados: total, fecha: new Date().toLocaleDateString('es-CO') } }];
""".strip()
        }),

        node("n_wa_sum2", "📨 Resumen a Juan Carlos", "n8n-nodes-base.httpRequest", 4, 2400, 300, {
            "method": "POST",
            "url": CT_JUAN_URL,
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                "content:'✅ Campaña mensual Proveedores completada"
                "\\n📊 Mensajes enviados: '+$json.total_enviados"
                "+'\\n📅 Fecha: '+$json.fecha,"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        node("n_nodata2", "⏭️ Sin Proveedores Hoy", "n8n-nodes-base.noOp", 1, 1200, 500, {}),
    ]

    pairs = [
        ("🗓️ Primer Lunes del Mes 9AM",       "📋 Obtener Proveedores",              0, 0),
        ("📋 Obtener Proveedores",              "🔧 Filtrar Cooldown 25 días",         0, 0),
        ("🔧 Filtrar Cooldown 25 días",         "❓ ¿Hay Proveedores?",               0, 0),
        ("❓ ¿Hay Proveedores?",                "📦 Procesar de a 1",                  0, 0),
        ("❓ ¿Hay Proveedores?",                "⏭️ Sin Proveedores Hoy",             1, 0),
        ("📦 Procesar de a 1",                  "➕ Crear Contacto Chatwoot",          0, 0),
        ("➕ Crear Contacto Chatwoot",           "📤 Crear Conversación con Template",  0, 0),
        ("📤 Crear Conversación con Template",  "📝 Registrar Envío",                  0, 0),
        ("📝 Registrar Envío",                  "📦 Procesar de a 1",                  0, 0),   # loop
        ("📦 Procesar de a 1",                  "📊 Contar Resultados",                1, 0),   # done
        ("📊 Contar Resultados",                "📨 Resumen a Juan Carlos",            0, 0),
    ]

    return workflow("La Falla | 02 - Outbound Mensual Proveedores", nodes, build_connections(pairs))


# ─── WF3: LinkedIn Borradores Semanales ───────────────────────────────────────

def wf3():
    nodes = [
        sticky("s3", 240, 60, CREDS_NOTE, w=540, h=300),

        node("n_sched3", "🗓️ Lunes 8AM - LinkedIn", "n8n-nodes-base.scheduleTrigger", 1, 240, 360, {
            "rule": {"interval": [{"field": "cronExpression"}]},
            "cronExpression": "0 13 * * 1",
        }),

        node("n_get3", "📋 Obtener Clientes", "n8n-nodes-base.httpRequest", 4, 480, 360, {
            "method": "GET",
            "url": "={{$env.FASTAPI_BASE_URL}}/stakeholders",
            "authentication": "none",
            **FASTAPI_HDRS,
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "clasificacion",        "value": "Clientes"},
                {"name": "sin_interaccion_dias", "value": "30"},
            ]},
        }),

        node("n_top5", N_TOP5, "n8n-nodes-base.code", 2, 720, 360, {
            "mode": "runOnceForAllItems",
            "jsCode": r"""
const raw = $input.all();
const list = Array.isArray(raw[0]?.json) ? raw[0].json : raw.map(i => i.json);

const sorted = list
  .sort((a, b) => (b.apariciones ?? 1) - (a.apariciones ?? 1))
  .slice(0, 5);

return sorted.map(s => ({ json: {
  id: s.id,
  nombre: s.nombre ?? '',
  rol: s.rol ?? '',
  servicios: s.servicios ?? '',
  observaciones: s.observaciones ?? '',
  redes: s.redes ?? '',
  apariciones: s.apariciones ?? 1,
}}));
""".strip()
        }),

        node("n_ifdata3", "❓ ¿Hay Clientes?", "n8n-nodes-base.if", 2, 960, 360, {
            "conditions": {"number": [{"value1": "={{$input.all().length}}", "operation": "larger", "value2": 0}]}
        }),

        node("n_batch3", "📦 Procesar de a 1", "n8n-nodes-base.splitInBatches", 3, 1200, 280, {
            "batchSize": 1, "options": {}
        }),

        node("n_draft", "🤖 IA: Generar Borrador LinkedIn", "n8n-nodes-base.httpRequest", 4, 1440, 280, {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "none",
            **OPENAI_HDRS,
            **jbody(
                "model:'gpt-4o-mini',"
                "temperature:0.7,"
                "max_tokens:300,"
                "messages:["
                  "{role:'system',content:'Eres el asistente de Juan Carlos, gerente comercial de "
                  "La Falla DF (productora de servicios audiovisuales en el Eje Cafetero, Colombia). "
                  "Redacta un mensaje de LinkedIn CORTO (máx 3 oraciones) en español, cálido y profesional, "
                  "para conectar con este contacto. El objetivo es que piensen en La Falla cuando "
                  "necesiten rodar en el Eje Cafetero. Usa detalles del perfil. Sin hashtags ni emojis.'},"
                  "{role:'user',content:'Contacto: '+$json.nombre"
                  "+'\\nRol: '+$json.rol"
                  "+'\\nServicios: '+$json.servicios"
                  "+'\\nNotas: '+$json.observaciones"
                  "+'\\nAparece en '+$json.apariciones+' de nuestros archivos (hot lead)'}"
                "]"
            ),
        }),

        node("n_parse3", "🔧 Parsear Borrador", "n8n-nodes-base.code", 2, 1680, 280, {
            "mode": "runOnceForEachItem",
            "jsCode": r"""
const draft = $input.item.json.choices?.[0]?.message?.content ?? '(sin borrador)';
const data = $('🏆 Top 5 Hot Leads').item.json;
return { json: {
  id: data.id,
  nombre: data.nombre,
  rol: data.rol,
  redes: data.redes,
  apariciones: data.apariciones,
  draft: draft.trim(),
}};
""".strip()
        }),

        node("n_agg3", "📋 Armar Mensaje WA", "n8n-nodes-base.code", 2, 1920, 280, {
            "mode": "runOnceForAllItems",
            "jsCode": r"""
const items = $input.all();
let msg = `📊 *Dashboard LinkedIn - ${new Date().toLocaleDateString('es-CO', {weekday:'long', day:'numeric', month:'long'})}*\n\n`;
msg += `Top ${items.length} clientes sin contacto en 30+ días:\n\n`;
items.forEach((item, i) => {
  const d = item.json;
  msg += `*${i+1}. ${d.nombre}* (${d.rol ?? 'sin rol'}) — 🔥×${d.apariciones}\n`;
  if (d.redes) msg += `LinkedIn: ${d.redes}\n`;
  msg += `💬 _${d.draft}_\n\n`;
});
msg += `Para registrar que enviaste: responde */enviado <ID>*`;
return [{ json: { message: msg } }];
""".strip()
        }),

        node("n_wa3", "📨 Enviar Borradores a JC", "n8n-nodes-base.httpRequest", 4, 2160, 280, {
            "method": "POST",
            "url": CT_JUAN_URL,
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                "content:$json.message,"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        node("n_nodata3", "⏭️ Sin Clientes Pendientes", "n8n-nodes-base.noOp", 1, 1200, 460, {}),
    ]

    pairs = [
        ("🗓️ Lunes 8AM - LinkedIn",          "📋 Obtener Clientes",              0, 0),
        ("📋 Obtener Clientes",               N_TOP5,                              0, 0),
        (N_TOP5,                              "❓ ¿Hay Clientes?",                0, 0),
        ("❓ ¿Hay Clientes?",                 "📦 Procesar de a 1",               0, 0),
        ("❓ ¿Hay Clientes?",                 "⏭️ Sin Clientes Pendientes",       1, 0),
        ("📦 Procesar de a 1",                "🤖 IA: Generar Borrador LinkedIn",  0, 0),
        ("🤖 IA: Generar Borrador LinkedIn",  "🔧 Parsear Borrador",              0, 0),
        ("🔧 Parsear Borrador",               "📦 Procesar de a 1",               0, 0),   # loop
        ("📦 Procesar de a 1",                "📋 Armar Mensaje WA",              1, 0),   # done
        ("📋 Armar Mensaje WA",               "📨 Enviar Borradores a JC",        0, 0),
    ]

    return workflow("La Falla | 03 - LinkedIn Borradores Semanales", nodes, build_connections(pairs))


# ─── WF4: LinkedIn Chrome Extension ───────────────────────────────────────────

def wf4():
    nodes = [
        sticky("s4", 240, 60,
            CREDS_NOTE + "\n\n**⚙️ Extensión Chrome:**\n"
            "Construir `chrome_ext_linkedin/` y configurar el webhook URL + FASTAPI_API_KEY.",
            w=540, h=340),

        node("n_wh4", "🔗 Webhook Chrome Extension", "n8n-nodes-base.webhook", 2, 240, 400, {
            "path": "linkedin-chrome-lafalla",
            "httpMethod": "POST",
            "responseMode": "lastNode",
        }),

        node("n_verify4", N_VFY4, "n8n-nodes-base.code", 2, 480, 400, {
            "mode": "runOnceForEachItem",
            "jsCode": r"""
const key = $input.item.json.headers?.['x-api-key']
         ?? $input.item.json.headers?.['X-Api-Key'] ?? '';
const expected = process.env.FASTAPI_API_KEY ?? '';
return { json: {
  authorized: expected !== '' && key === expected,
  linkedin_url: $input.item.json.body?.linkedin_url ?? '',
  nombre:       $input.item.json.body?.nombre ?? '',
  headline:     $input.item.json.body?.headline ?? '',
  empresa:      $input.item.json.body?.empresa ?? '',
}};
""".strip()
        }),

        node("n_ifauth4", "🔐 ¿Autorizado?", "n8n-nodes-base.if", 2, 720, 400, {
            "conditions": {"boolean": [{"value1": "={{$json.authorized}}", "operation": "true"}]}
        }),

        node("n_check4", "🔍 ¿Existe en Base?", "n8n-nodes-base.httpRequest", 4, 960, 300, {
            "method": "GET",
            "url": "={{$env.FASTAPI_BASE_URL}}/stakeholders",
            "authentication": "none",
            **FASTAPI_HDRS,
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "linkedin_url", "value": "={{$json.linkedin_url}}"},
            ]},
            "onError": "continueErrorOutput",
        }),

        node("n_ifexists", "❓ ¿Ya Existe?", "n8n-nodes-base.if", 2, 1200, 300, {
            "conditions": {"number": [{"value1": "={{($json ?? []).length}}", "operation": "larger", "value2": 0}]}
        }),

        node("n_wa_new4", "💬 Preguntar a JC (Nuevo)", "n8n-nodes-base.httpRequest", 4, 1440, 200, {
            "method": "POST",
            "url": CT_JUAN_URL,
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                f"content:'👤 Detecté que contactaste a *'+$('{N_VFY4}').item.json.nombre"
                f"+'* ('+$('{N_VFY4}').item.json.headline+') en LinkedIn y no está en la base."
                "\\n\\n¿Lo guardo?"
                f"\\n• `/agregar '+$('{N_VFY4}').item.json.nombre+', '+$('{N_VFY4}').item.json.headline+'` para guardar"
                "\\n• O ignora este mensaje,"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        node("n_wa_exists4", "💬 Notificar Que Ya Existe", "n8n-nodes-base.httpRequest", 4, 1440, 400, {
            "method": "POST",
            "url": CT_JUAN_URL,
            "authentication": "none",
            **CHATWOOT_HDRS,
            **jbody(
                f"content:'ℹ️ *'+$('{N_VFY4}').item.json.nombre+'* ya está en la base de datos.',"
                "message_type:'outgoing',"
                "private:false"
            ),
        }),

        node("n_resp4_ok", "✅ Respuesta 200 OK", "n8n-nodes-base.set", 3, 960, 540, {
            "mode": "manual",
            "assignments": {"assignments": [
                {"name": "status",  "value": "ok",        "type": "string"},
                {"name": "message", "value": "processed", "type": "string"},
            ]},
        }),

        node("n_resp4_deny", "🚫 Respuesta 401", "n8n-nodes-base.set", 3, 720, 540, {
            "mode": "manual",
            "assignments": {"assignments": [
                {"name": "status", "value": "unauthorized", "type": "string"},
            ]},
        }),

        node("n_whr4", "📤 Webhook Response", "n8n-nodes-base.respondToWebhook", 1, 1200, 540, {
            "respondWith": "json",
            "responseBody": "={{$json}}",
            "options": {"responseCode": 200},
        }),
    ]

    pairs = [
        ("🔗 Webhook Chrome Extension", N_VFY4,                        0, 0),
        (N_VFY4,                        "🔐 ¿Autorizado?",             0, 0),
        ("🔐 ¿Autorizado?",             "🔍 ¿Existe en Base?",         0, 0),
        ("🔐 ¿Autorizado?",             "🚫 Respuesta 401",            1, 0),
        ("🔍 ¿Existe en Base?",         "❓ ¿Ya Existe?",              0, 0),
        ("❓ ¿Ya Existe?",              "💬 Notificar Que Ya Existe",  0, 0),
        ("❓ ¿Ya Existe?",              "💬 Preguntar a JC (Nuevo)",   1, 0),
        ("💬 Preguntar a JC (Nuevo)",   "✅ Respuesta 200 OK",         0, 0),
        ("💬 Notificar Que Ya Existe",  "✅ Respuesta 200 OK",         0, 0),
        ("✅ Respuesta 200 OK",         "📤 Webhook Response",         0, 0),
        ("🚫 Respuesta 401",            "📤 Webhook Response",         0, 0),
    ]

    return workflow("La Falla | 04 - LinkedIn Chrome Extension", nodes, build_connections(pairs))


# ─── WF5: Registrar Interacción Manual ────────────────────────────────────────

def wf5():
    nodes = [
        sticky("s5", 240, 60,
            "## WF5 — Registrar Interacción Manual\n\n"
            "Endpoint genérico para registrar interacciones desde Google Sheet u otras fuentes.\n\n"
            "**Payload esperado:**\n"
            "```json\n"
            "{\n"
            '  "stakeholder_id": 123,\n'
            '  "campaign": "whatsapp_aliados_ondemand",\n'
            '  "canal": "whatsapp",\n'
            '  "direccion": "out",\n'
            '  "mensaje": "contacto sobre proyecto X",\n'
            '  "status": "sent"\n'
            "}\n"
            "```\n\n"
            "**Auth:** Header `X-Api-Key` = `FASTAPI_API_KEY`\n\n"
            "**URL webhook:**\n"
            "`<N8N_HOST>/webhook/registrar-interaccion-lafalla`",
            color=3, w=500, h=320),

        node("n_wh5", "🔗 Webhook Registrar Interacción", "n8n-nodes-base.webhook", 2, 240, 420, {
            "path": "registrar-interaccion-lafalla",
            "httpMethod": "POST",
            "responseMode": "lastNode",
        }),

        node("n_auth5", "🔐 Verificar API Key", "n8n-nodes-base.code", 2, 480, 420, {
            "mode": "runOnceForEachItem",
            "jsCode": r"""
const key = $input.item.json.headers?.['x-api-key']
         ?? $input.item.json.headers?.['X-Api-Key'] ?? '';
const expected = process.env.FASTAPI_API_KEY ?? '';
return { json: {
  authorized: expected !== '' && key === expected,
  payload: $input.item.json.body ?? {},
}};
""".strip()
        }),

        node("n_ifauth5", "🔐 ¿Autorizado?", "n8n-nodes-base.if", 2, 720, 420, {
            "conditions": {"boolean": [{"value1": "={{$json.authorized}}", "operation": "true"}]}
        }),

        node("n_log5", "📝 Registrar en FastAPI", "n8n-nodes-base.httpRequest", 4, 960, 320, {
            "method": "POST",
            "url": "={{$env.FASTAPI_BASE_URL}}/interactions",
            "authentication": "none",
            **FASTAPI_HDRS,
            **jbody(
                "stakeholder_id:$json.payload.stakeholder_id??null,"
                "campaign:$json.payload.campaign??'manual',"
                "canal:$json.payload.canal??'whatsapp',"
                "direccion:$json.payload.direccion??'out',"
                "mensaje:$json.payload.mensaje??'',"
                "status:$json.payload.status??'sent'"
            ),
        }),

        node("n_resp5_ok", "✅ Set Respuesta OK", "n8n-nodes-base.set", 3, 1200, 320, {
            "mode": "manual",
            "assignments": {"assignments": [
                {"name": "status",  "value": "ok",                     "type": "string"},
                {"name": "message", "value": "Interacción registrada", "type": "string"},
            ]},
        }),

        node("n_resp5_err", "🚫 Set Respuesta 401", "n8n-nodes-base.set", 3, 960, 540, {
            "mode": "manual",
            "assignments": {"assignments": [
                {"name": "status",  "value": "unauthorized",    "type": "string"},
                {"name": "message", "value": "API key inválida", "type": "string"},
            ]},
        }),

        node("n_whr5", "📤 Webhook Response", "n8n-nodes-base.respondToWebhook", 1, 1440, 420, {
            "respondWith": "json",
            "responseBody": "={{$json}}",
            "options": {"responseCode": 200},
        }),
    ]

    pairs = [
        ("🔗 Webhook Registrar Interacción", "🔐 Verificar API Key",    0, 0),
        ("🔐 Verificar API Key",             "🔐 ¿Autorizado?",         0, 0),
        ("🔐 ¿Autorizado?",                  "📝 Registrar en FastAPI", 0, 0),
        ("🔐 ¿Autorizado?",                  "🚫 Set Respuesta 401",    1, 0),
        ("📝 Registrar en FastAPI",          "✅ Set Respuesta OK",      0, 0),
        ("✅ Set Respuesta OK",              "📤 Webhook Response",      0, 0),
        ("🚫 Set Respuesta 401",             "📤 Webhook Response",      0, 0),
    ]

    return workflow("La Falla | 05 - Registrar Interacción Manual", nodes, build_connections(pairs))


# ─── Main ─────────────────────────────────────────────────────────────────────

WORKFLOWS = [wf1, wf2, wf3, wf4, wf5]
FILENAMES = [
    "01_alta_contacto_whatsapp.json",
    "02_outbound_proveedores_mensual.json",
    "03_linkedin_borradores_semanales.json",
    "04_linkedin_chrome_extension.json",
    "05_registrar_interaccion.json",
]

def _load_env():
    env_path = __file__
    for _ in range(2):
        env_path = os.path.dirname(env_path)
    env_file = os.path.join(env_path, ".env")
    if os.path.exists(env_file):
        for line in open(env_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

if __name__ == "__main__":
    import pathlib
    _load_env()

    out_dir = pathlib.Path(__file__).parent

    for fn, wf_fn in zip(FILENAMES, WORKFLOWS):
        wf_data = wf_fn()
        path = out_dir / fn
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wf_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Generado: {fn}")

    if "--push" not in sys.argv:
        sys.exit(0)

    import urllib.request
    import urllib.error

    host    = os.environ.get("N8N_HOST", "").rstrip("/")
    api_key = os.environ.get("N8N_API_KEY", "")
    if not host or not api_key:
        print("❌ Faltan N8N_HOST o N8N_API_KEY")
        sys.exit(1)

    base_headers = {"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}

    def n8n_req(method, path, data=None):
        req = urllib.request.Request(
            f"{host}/api/v1{path}",
            data=json.dumps(data).encode() if data else None,
            headers=base_headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    print("\n🗑️  Borrando workflows existentes de La Falla DF...")
    try:
        existing = n8n_req("GET", "/workflows?limit=100")
        wf_list = existing.get("data", existing) if isinstance(existing, dict) else existing
        for wf in wf_list:
            if "La Falla" in wf.get("name", ""):
                wf_id = wf["id"]
                try:
                    n8n_req("DELETE", f"/workflows/{wf_id}")
                    print(f"   Borrado: {wf['name']} (ID {wf_id})")
                except Exception as e:
                    print(f"   ⚠️  No se pudo borrar {wf_id}: {e}")
    except Exception as e:
        print(f"   ⚠️  No se pudo listar workflows: {e}")

    tag_id = None
    try:
        tags = n8n_req("GET", "/tags")
        tag_list = tags.get("data", tags) if isinstance(tags, dict) else tags
        for t in tag_list:
            if t.get("name") == "La Falla DF":
                tag_id = t["id"]
                break
        if not tag_id:
            new_tag = n8n_req("POST", "/tags", {"name": "La Falla DF"})
            tag_id = new_tag.get("id")
            print(f"\n🏷️  Tag 'La Falla DF' creado (ID {tag_id})")
        else:
            print(f"\n🏷️  Tag 'La Falla DF' existente (ID {tag_id})")
    except Exception as e:
        print(f"   ⚠️  No se pudo gestionar tags: {e}")

    print("\n📤 Publicando workflows...")
    for fn in FILENAMES:
        path = out_dir / fn
        with open(path, "rb") as f:
            data = json.loads(f.read())
        data.pop("tags", None)
        req = urllib.request.Request(
            f"{host}/api/v1/workflows",
            data=json.dumps(data).encode(),
            headers=base_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                wf_id = result.get("id", "?")
            if tag_id and wf_id != "?":
                try:
                    n8n_req("PUT", f"/workflows/{wf_id}/tags", [{"id": tag_id}])
                    tag_ok = " [tag: La Falla DF]"
                except Exception:
                    tag_ok = " [tag: no aplicado]"
            else:
                tag_ok = ""
            print(f"✅ {fn}\n   → ID: {wf_id}{tag_ok} | {host}/workflow/{wf_id}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"❌ Error en {fn}: HTTP {e.code} — {body[:300]}")
        except Exception as e:
            print(f"❌ Error en {fn}: {e}")
