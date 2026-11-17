import http from 'node:http';
import crypto from 'node:crypto';
import pg from 'pg';

const PORT = Number(process.env.PORT || 10000);
const BASE = (process.env.APP_BASE_URL || '').replace(/\/$/, '');
const CLIENT_ID = process.env.GOOGLE_CLIENT_ID || '';
const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET || '';
const ALLOWED = (process.env.ALLOWED_GMAIL || '').trim().toLowerCase();
const PASSWORD = process.env.ADMIN_PASSWORD || '';
const SESSION_SECRET = process.env.SESSION_SECRET || '';
const ENC_HEX = process.env.TOKEN_ENCRYPTION_KEY || '';
const DB = process.env.DATABASE_URL || '';
const COOKIE = 'vc_admin';
const STATE = 'vc_oauth_state';
const HOURS = 12;
const SCOPES = 'openid email https://www.googleapis.com/auth/gmail.send';
const CALLBACK = BASE + '/auth/google/callback';
let pool;
let databaseReady = false;
const ready = !!(BASE.startsWith('https://') && CLIENT_ID && CLIENT_SECRET && ALLOWED && PASSWORD.length >= 12 && SESSION_SECRET.length >= 32 && /^[0-9a-f]{64}$/i.test(ENC_HEX) && DB);
const key = /^[0-9a-f]{64}$/i.test(ENC_HEX) ? Buffer.from(ENC_HEX, 'hex') : null;

if (ready) {
  pool = new pg.Pool({connectionString: DB, max: 3, connectionTimeoutMillis: 6000, ssl: DB.includes('sslmode=disable') ? false : {rejectUnauthorized:false}});
  pool.query('CREATE TABLE IF NOT EXISTS vc_gmail_oauth (account TEXT PRIMARY KEY, ciphertext TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())')
  .then(() => {databaseReady = true; console.log('OAuth database initialized');})
  .catch(err => {console.error('OAuth database unavailable:', err.message);});
}
function cookies(req) {
  const obj = {};
  (req.headers.cookie || '').split(';').forEach(part => {const pos = part.indexOf('='); if (pos >= 0) obj[part.slice(0,pos).trim()] = part.slice(pos+1).trim();});
  return obj;
}
function safeEqual(a,b) {
  const x = Buffer.from(String(a)); const y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x,y);
}
function hmac(v) {return crypto.createHmac('sha256', SESSION_SECRET).update(v).digest('base64url');}
function logged(req) {
  if (!SESSION_SECRET) return false;
  const value = cookies(req)[COOKIE] || '';
  const parts = value.split('.');
  if (parts.length !== 3 || parts[0] !== 'v1') return false;
  const until = Number(parts[1]);
  return Number.isFinite(until) && until > Date.now() && safeEqual(hmac(parts[0]+'.'+parts[1]),parts[2]);
}
function adminCookie() {
  const data = 'v1.' + (Date.now()+HOURS*3600000);
  return COOKIE+'='+data+'.'+hmac(data)+'; Path=/; Max-Age='+(HOURS*3600)+'; HttpOnly; Secure; SameSite=Lax';
}
function escape(s) {return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function headers(other={}) {return {'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Cache-Control':'no-store',...other};}
function send(res,status,body,extra={}) {res.writeHead(status,headers({'Content-Type':'text/html; charset=utf-8',...extra}));res.end(body);}
function redirect(res,path,cookie) {res.writeHead(303,headers({'Location':path,...(cookie?{'Set-Cookie':cookie}:{})}));res.end();}
function page(title,main) {
  return '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+' · Vistoria Cloud</title><style>body{margin:0;background:#f2f7f4;color:#1e4334;font:15px/1.6 system-ui,Arial}.wrap{max-width:650px;margin:7vh auto;padding:16px}.card{background:#fff;border:1px solid #d6e8de;border-radius:18px;padding:clamp(22px,5vw,38px);box-shadow:0 10px 35px #12352212}h1{margin:0 0 12px;font-size:26px}p{color:#53695e}a{color:#137c57}button,.btn{display:inline-block;background:#137c57;border:0;border-radius:9px;color:white;text-decoration:none;padding:11px 17px;font-weight:700;cursor:pointer}input{display:block;border:1px solid #b9d7c5;padding:12px;border-radius:9px;width:100%;box-sizing:border-box;margin:8px 0 18px}.notice{background:#f6fbf8;border:1px solid #d7e9df;padding:15px;border-radius:10px;margin:18px 0}.foot{font-size:12px;color:#779085;margin-top:24px}</style></head><body><div class="wrap"><div class="card"><h1>'+escape(title)+'</h1>'+main+'<p class="foot">Vistoria Cloud · Conexão Google OAuth · Sem envio automático ativo</p></div></div></body></html>';
}
async function body(req) {
  let data = '';
  for await(const part of req){data+=part;if(data.length>12000)throw Error('Formulário muito grande');}
  return new URLSearchParams(data);
}
function sameOrigin(req) {
  const origin = req.headers.origin;
  if (origin && BASE && origin !== BASE) return false;
  const referer = req.headers.referer;
  if (referer && BASE && !referer.startsWith(BASE + '/')) return false;
  return true;
}
async function tokenStore(refresh) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm',key,iv);
  const encrypted = Buffer.concat([cipher.update(refresh,'utf8'),cipher.final()]);
  const value = [iv,cipher.getAuthTag(),encrypted].map(b=>b.toString('base64url')).join('.');
  await pool.query('INSERT INTO vc_gmail_oauth(account,ciphertext) VALUES($1,$2) ON CONFLICT (account) DO UPDATE SET ciphertext=EXCLUDED.ciphertext, updated_at=now()', [ALLOWED,value]);
}
async function connected() {
  if (!databaseReady) return false;
  const r = await pool.query('SELECT 1 FROM vc_gmail_oauth WHERE account=$1',[ALLOWED]);
  return !!r.rowCount;
}
function fail(res,message,status=400) {return send(res,status,page('Não foi possível continuar','<p>'+escape(message)+'</p><p><a href="/">Voltar ao painel de conexão</a></p>'));}
const server=http.createServer(async(req,res)=>{
  try {
    const url = new URL(req.url,'http://localhost');
    const path=url.pathname;
    if(path==='/health') {
      res.writeHead(200,headers({'Content-Type':'application/json'}));res.end(JSON.stringify({ok:true,oauthReady:ready&&databaseReady}));return;
    }
    if(path==='/login'&&req.method==='POST') {
      if(!ready || !sameOrigin(req))return fail(res,'Configuração indisponível.',403);
      const form=await body(req);const supplied=form.get('password')||'';
      if(!safeEqual(crypto.scryptSync(supplied,'vc-admin',64).toString('hex'),crypto.scryptSync(PASSWORD,'vc-admin',64).toString('hex')))return fail(res,'Senha incorreta.',401);
      return redirect(res,'/',adminCookie());
    }
    if(path==='/logout'&&req.method==='POST') {
      if(!sameOrigin(req))return fail(res,'Requisição recusada.',403);
      return redirect(res,'/',COOKIE+'=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax');
    }
    if(path==='/auth/google/start') {
      if(!ready||!databaseReady)return fail(res,'O Google e o banco ainda não estão configurados.',503);
      if(!logged(req))return redirect(res,'/');
      const nonce=crypto.randomBytes(30).toString('base64url');
      const authUrl=new URL('https://accounts.google.com/o/oauth2/v2/auth');
      for(const [k,v] of Object.entries({client_id:CLIENT_ID,redirect_uri:CALLBACK,response_type:'code',scope:SCOPES,access_type:'offline',prompt:'consent',state:nonce}))authUrl.searchParams.set(k,v);
      return redirect(res,authUrl.toString(),STATE+'='+nonce+'; Path=/auth/google; Max-Age=600; HttpOnly; Secure; SameSite=Lax');
    }
    if(path==='/auth/google/callback') {
      if(!ready||!databaseReady||!logged(req))return fail(res,'Sessão expirada ou serviço não configurado.',403);
      const saved=cookies(req)[STATE]||'';
      const state=url.searchParams.get('state')||'';
      if(!saved||!state||!safeEqual(saved,state))return fail(res,'Autorização expirada ou inválida. Comece novamente.',403);
      if(url.searchParams.get('error'))return fail(res,'Autorização cancelada pelo Google: '+url.searchParams.get('error'),400);
      const code=url.searchParams.get('code');
      if(!code)return fail(res,'Google não forneceu o código de autorização.');
      const tokenResp=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({code,client_id:CLIENT_ID,client_secret:CLIENT_SECRET,redirect_uri:CALLBACK,grant_type:'authorization_code'})});
      const tokens=await tokenResp.json();
      if(!tokenResp.ok||!tokens.access_token)return fail(res,'O Google recusou a troca de código. Verifique o client ID, secret e URI de redirecionamento.');
      const infoResp=await fetch('https://openidconnect.googleapis.com/v1/userinfo',{headers:{Authorization:'Bearer '+tokens.access_token}});
      const info=await infoResp.json();
      const email=String(info.email||'').toLowerCase();
      if(!infoResp.ok || !info.email_verified || !email || email!==ALLOWED)return fail(res,'Esta conta não está na lista autorizada. Use o Gmail configurado como ALLOWED_GMAIL.',403);
      if(!tokens.refresh_token)return fail(res,'O Google não retornou um token para conexão permanente. Revogue o acesso anterior e autorize novamente.');
      await tokenStore(tokens.refresh_token);
      return redirect(res,'/?connected=1',STATE+'=; Path=/auth/google; Max-Age=0; HttpOnly; Secure; SameSite=Lax');
    }
    if(path==='/disconnect'&&req.method==='POST') {
      if(!ready||!databaseReady||!logged(req)||!sameOrigin(req))return fail(res,'Ação não autorizada.',403);
      await pool.query('DELETE FROM vc_gmail_oauth WHERE account=$1',[ALLOWED]);
      return redirect(res,'/?disconnected=1');
    }
    if(path==='/'&&req.method==='GET') {
      if(!ready)return send(res,200,page('Configuração do Gmail pendente','<p>O serviço de conexão foi instalado, mas ainda precisa de configurações privadas antes de autorizar sua conta.</p><div class="notice"><strong>Configure as variáveis na Render:</strong><p>APP_BASE_URL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ALLOWED_GMAIL, ADMIN_PASSWORD, SESSION_SECRET, TOKEN_ENCRYPTION_KEY e DATABASE_URL.</p><p>URI de redirecionamento para cadastrar no Google Cloud:</p><p><code>'+escape(CALLBACK||'[URL do serviço]/auth/google/callback')+'</code></p></div><p>Depois da configuração, abra novamente esta página.</p>'));
      if(!databaseReady)return send(res,503,page('Aguardando banco de dados','<p>As configurações foram encontradas, mas o armazenamento seguro ainda não está disponível. Confira DATABASE_URL na Render.</p>'));
      if(!logged(req))return send(res,200,page('Acesso administrativo','<p>Entre com a senha configurada no serviço. Nunca forneça sua senha do Gmail aqui.</p><form method="post" action="/login"><label>Senha do painel<input type="password" name="password" autocomplete="current-password" required minlength="12"></label><button type="submit">Entrar</button></form>'));
      const has=await connected();
      let main='<p>Conta permitida: <strong>'+escape(ALLOWED)+'</strong>.</p>';
      if(has)main+='<div class="notice"><strong>Gmail conectado com autorização segura.</strong><p>Token guardado criptografado no banco. Nenhuma campanha será disparada automaticamente nesta etapa.</p></div><form method="post" action="/disconnect"><button type="submit">Desconectar Gmail</button></form>';
      else main+='<div class="notice"><strong>Gmail ainda não conectado.</strong><p>Você será levado à página oficial do Google para permitir apenas o envio de mensagens.</p></div><p><a class="btn" href="/auth/google/start">Conectar Gmail</a></p>';
      main+='<form method="post" action="/logout" style="margin-top:22px"><button type="submit" style="background:#547568">Sair</button></form>';
      if(url.searchParams.has('connected'))main='<div class="notice">Autorização concluída.</div>'+main;
      return send(res,200,page('Conexão Gmail · Vistoria Cloud',main));
    }
    return fail(res,'Página não encontrada.',404);
  } catch(err) {console.error('Request failed:',err.message);return fail(res,'O serviço apresentou um problema interno. Confira os registros da hospedagem.',500);}
});
server.listen(PORT,()=>console.log('Gmail OAuth connection service listening at port '+PORT));