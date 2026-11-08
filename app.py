import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from decimal import Decimal, InvalidOperation
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from pymongo import MongoClient, ReturnDocument, ASCENDING
from pymongo.errors import PyMongoError
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'solo-desarrollo-cambiar-en-produccion')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('RENDER') == 'true')
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    raise RuntimeError('Configura MONGO_URI en .env o en Render')
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000, tz_aware=True)
db = client[os.getenv('MONGO_DB', 'solestyle_calzado')]
productos = db['productos']; reservas = db['reservas']; pedidos = db['pedidos']; usuarios = db['usuarios']
DURACION = 300


def ahora():
    return datetime.now(timezone.utc)


def oid(valor):
    try: return ObjectId(valor)
    except Exception: abort(404)


def folio():
    if 'reserva_id' not in session: session['reserva_id'] = uuid.uuid4().hex
    return session['reserva_id']


def usuario_actual():
    if 'usuario_id' not in session: return None
    return usuarios.find_one({'_id': oid(session['usuario_id'])})


def login_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not usuario_actual():
            flash('Inicia sesión para continuar.', 'warning'); return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return inner


def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        user = usuario_actual()
        if not user or not user.get('admin'): abort(403)
        return fn(*args, **kwargs)
    return inner


def validar_producto(data):
    nombre = str(data.get('nombre', '')).strip()
    categoria = str(data.get('categoria', '')).strip()
    talla = str(data.get('talla', '')).strip()
    descripcion = str(data.get('descripcion', '')).strip()
    imagen = str(data.get('imagen', '')).strip()
    if not nombre or len(nombre)>100 or not talla or not categoria: raise ValueError('Nombre, categoría y talla son obligatorios.')
    try:
        precio = Decimal(str(data.get('precio', '')))
        stock = int(data.get('existencias', 0))
        if not precio.is_finite() or precio <= 0 or stock < 0: raise ValueError()
    except (ValueError, InvalidOperation): raise ValueError('Precio positivo y existencias no negativas requeridos.')
    if imagen and not imagen.startswith(('https://','http://')): raise ValueError('La imagen debe usar una URL http(s).')
    return dict(nombre=nombre, categoria=categoria, talla=talla, descripcion=descripcion, imagen=imagen, precio=float(precio), existencias=stock)


def producto_publico(p):
    return dict(id=str(p['_id']), nombre=p['nombre'], categoria=p.get('categoria',''), talla=p.get('talla',''), precio=p['precio'], descripcion=p.get('descripcion',''), imagen=p.get('imagen',''), existencias=p.get('existencias',0), reservadas=p.get('reservadas',0), disponibles=max(0,p.get('existencias',0)-p.get('reservadas',0)))


def inicializar():
    usuarios.create_index('correo', unique=True)
    reservas.create_index([('reserva_id',ASCENDING),('estado',ASCENDING)])
    reservas.create_index([('estado',ASCENDING),('vence_en',ASCENDING)])
    pedidos.create_index('reserva_doc_id', unique=True)
    # Inicializa documentos anteriores sin alterar cantidades existentes.
    productos.update_many({'reservadas': {'$exists': False}}, {'$set': {'reservadas':0}})


def liberar_vencidas():
    # CAS por estado: solo un proceso puede liberar cada reserva una vez.
    # Las transacciones mantienen la reserva y el inventario sincronizados.
    vencidas = reservas.find({'estado':'activa','vence_en':{'$lte':ahora()}}, {'_id':1}).limit(100)
    for r in vencidas:
        try:
            with client.start_session() as s:
                with s.start_transaction():
                    doc = reservas.find_one_and_update({'_id':r['_id'],'estado':'activa','vence_en':{'$lte':ahora()}}, {'$set':{'estado':'vencida','cerrada_en':ahora()}}, session=s, return_document=ReturnDocument.AFTER)
                    if doc:
                        for item in doc['items']:
                            productos.update_one({'_id':item['producto_id']}, {'$inc':{'reservadas':-item['cantidad']}}, session=s)
        except PyMongoError:
            app.logger.exception('Error liberando reserva vencida')


@app.before_request
def preparar():
    folio()
    # Se ejecuta al entrar; también se ignora el plazo vencido en operaciones de confirmación.
    if request.endpoint != 'static':
        liberar_vencidas()
        if 'usuario_id' in session:
            ultima = reservas.find_one({'reserva_id':folio(),'usuario_id':oid(session['usuario_id']),'estado':'vencida'}, sort=[('cerrada_en',-1)])
            if ultima and session.get('vencida_notificada') != str(ultima['_id']):
                session['vencida_notificada'] = str(ultima['_id'])
                flash('La reserva venció. Las existencias fueron devueltas.', 'warning')


@app.context_processor
def contexto():
    return dict(usuario=usuario_actual(), carrito_count=sum(session.get('carrito',{}).values()))


@app.route('/')
def index():
    return render_template('index.html', productos=[producto_publico(p) for p in productos.find().sort('nombre',1)])


@app.route('/producto/<id>')
def detalle(id):
    p = productos.find_one({'_id':oid(id)})
    if not p: abort(404)
    return render_template('detalle.html', p=producto_publico(p))


@app.post('/carrito/agregar/<id>')
def agregar_carrito(id):
    p = productos.find_one({'_id':oid(id)})
    if not p: abort(404)
    if not usuario_actual(): flash('Inicia sesión para comprar.', 'warning'); return redirect(url_for('login'))
    if reservas.find_one({'reserva_id':folio(),'estado':'activa'}):
        flash('Primero confirma o cancela tu reserva activa.', 'warning'); return redirect(url_for('carrito'))
    cantidad = max(1,min(99,int(request.form.get('cantidad',1))))
    cart = session.get('carrito',{}); cart[id] = cart.get(id,0)+cantidad; session['carrito']=cart
    flash('Calzado agregado al carrito.', 'success'); return redirect(url_for('carrito'))


@app.post('/carrito/quitar/<id>')
def quitar_carrito(id):
    cart=session.get('carrito',{}); cart.pop(id,None); session['carrito']=cart
    return redirect(url_for('carrito'))


def carrito_items():
    cart=session.get('carrito',{}); ids=[oid(x) for x in cart]
    encontrados={str(p['_id']):p for p in productos.find({'_id':{'$in':ids}})}
    return [dict(**producto_publico(encontrados[k]),cantidad=v,subtotal=round(encontrados[k]['precio']*v,2)) for k,v in cart.items() if k in encontrados and isinstance(v,int) and v>0]


@app.route('/carrito')
@login_required
def carrito():
    items=carrito_items(); r=reservas.find_one({'reserva_id':folio(),'estado':'activa'})
    return render_template('carrito.html', items=items, total=round(sum(x['subtotal'] for x in items),2), reserva=r)


@app.post('/reservar')
@login_required
def reservar():
    items=carrito_items()
    if not items: flash('Tu carrito está vacío.', 'warning'); return redirect(url_for('carrito'))
    try:
        with client.start_session() as s:
            with s.start_transaction():
                if reservas.find_one({'reserva_id':folio(),'estado':'activa'},session=s): raise ValueError('Ya tienes una reserva activa.')
                docs=[]; total=0
                for item in items:
                    # Disponibilidad condicionada ATÓMICAMENTE en Atlas.
                    p=productos.find_one_and_update({'_id':oid(item['id']), '$expr':{'$gte':[{'$subtract':['$existencias','$reservadas']},item['cantidad']]}}, {'$inc':{'reservadas':item['cantidad']}}, session=s, return_document=ReturnDocument.AFTER)
                    if not p: raise ValueError('No hay existencias suficientes para completar el carrito.')
                    docs.append(dict(producto_id=p['_id'],nombre=p['nombre'],talla=p.get('talla',''),cantidad=item['cantidad'],precio=p['precio']))
                    total+=p['precio']*item['cantidad']
                t=ahora()
                reservas.insert_one(dict(reserva_id=folio(), usuario_id=oid(session['usuario_id']), items=docs, recurso_id=docs[0]['producto_id'], cantidad=sum(x['cantidad'] for x in docs), estado='activa', creada_en=t, vence_en=t+timedelta(seconds=DURACION), total=round(total,2)),session=s)
        flash('Reserva creada por 5 minutos.', 'success')
    except (PyMongoError,ValueError) as e:
        app.logger.warning('Reserva rechazada: %s',e)
        flash(str(e) if isinstance(e,ValueError) else 'No fue posible reservar; inténtalo nuevamente.', 'danger')
    return redirect(url_for('carrito'))


def cerrar_reserva(accion):
    try:
        with client.start_session() as s:
            with s.start_transaction():
                filtro={'reserva_id':folio(),'usuario_id':oid(session['usuario_id']),'estado':'activa'}
                if accion=='confirmar': filtro['vence_en']={'$gt':ahora()}
                r=reservas.find_one_and_update(filtro, {'$set':{'estado':'confirmada' if accion=='confirmar' else 'cancelada','cerrada_en':ahora()}}, session=s, return_document=ReturnDocument.AFTER)
                if not r: raise ValueError('No existe una reserva activa válida o ya venció.')
                for item in r['items']:
                    cambio={'reservadas':-item['cantidad']}
                    if accion=='confirmar': cambio['existencias']=-item['cantidad']
                    productos.update_one({'_id':item['producto_id']},{'$inc':cambio},session=s)
                if accion=='confirmar':
                    pedidos.insert_one(dict(reserva_doc_id=r['_id'], usuario_id=r['usuario_id'], items=r['items'], total=r['total'], fecha=ahora(), estado='Simulada'),session=s)
        if accion=='confirmar': session['carrito']={}
        flash('¡Compra simulada confirmada! No se realizó ningún cobro.' if accion=='confirmar' else 'Reserva cancelada. Existencias devueltas.', 'success')
        return redirect(url_for('mis_compras') if accion=='confirmar' else url_for('carrito'))
    except (PyMongoError,ValueError) as e:
        app.logger.warning('No se pudo cerrar reserva: %s',e)
        flash(str(e) if isinstance(e,ValueError) else 'No se pudo procesar la operación.', 'danger')
        return redirect(url_for('carrito'))


@app.post('/reserva/confirmar')
@login_required
def confirmar(): return cerrar_reserva('confirmar')


@app.post('/reserva/cancelar')
@login_required
def cancelar(): return cerrar_reserva('cancelar')


@app.route('/mis-compras')
@login_required
def mis_compras():
    return render_template('compras.html', pedidos=list(pedidos.find({'usuario_id':oid(session['usuario_id'])}).sort('fecha',-1)))


@app.route('/registro',methods=['GET','POST'])
def registro():
    if request.method=='POST':
        nombre=request.form.get('nombre','').strip(); correo=request.form.get('correo','').strip().lower(); clave=request.form.get('clave','')
        if not nombre or '@' not in correo or len(clave)<8: flash('Datos inválidos; contraseña de mínimo 8 caracteres.','danger')
        else:
            try:
                usuarios.insert_one(dict(nombre=nombre,correo=correo,clave_hash=generate_password_hash(clave),admin=False))
                flash('Cuenta creada. Inicia sesión.','success'); return redirect(url_for('login'))
            except PyMongoError: flash('No se pudo crear la cuenta. Verifica si el correo ya existe.','danger')
    return render_template('auth.html', registro=True)


@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=usuarios.find_one({'correo':request.form.get('correo','').strip().lower()})
        if u and check_password_hash(u['clave_hash'],request.form.get('clave','')):
            session.clear(); session['usuario_id']=str(u['_id']); session['reserva_id']=uuid.uuid4().hex
            return redirect(url_for('index'))
        flash('Credenciales incorrectas.','danger')
    return render_template('auth.html', registro=False)


@app.post('/salir')
def salir(): session.clear(); return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin(): return render_template('admin.html', productos=[producto_publico(p) for p in productos.find().sort('nombre',1)])


@app.route('/admin/producto/nuevo',methods=['GET','POST'])
@admin_required
def nuevo():
    if request.method=='POST':
        try:
            data=validar_producto(request.form); data['reservadas']=0; productos.insert_one(data)
            flash('Producto creado.','success'); return redirect(url_for('admin'))
        except ValueError as e: flash(str(e),'danger')
    return render_template('form_producto.html', p=None)


@app.route('/admin/producto/<id>/editar',methods=['GET','POST'])
@admin_required
def editar(id):
    p=productos.find_one({'_id':oid(id)})
    if not p: abort(404)
    if request.method=='POST':
        try:
            data=validar_producto(request.form)
            if data['existencias']<p.get('reservadas',0): raise ValueError('No puedes reducir el stock por debajo de las unidades reservadas.')
            productos.update_one({'_id':p['_id'],'reservadas':{'$lte':data['existencias']}},{'$set':data})
            flash('Producto actualizado.','success'); return redirect(url_for('admin'))
        except ValueError as e: flash(str(e),'danger')
    return render_template('form_producto.html',p=producto_publico(p))


@app.post('/admin/producto/<id>/eliminar')
@admin_required
def eliminar(id):
    p=productos.find_one({'_id':oid(id)})
    if p and p.get('reservadas',0)==0: productos.delete_one({'_id':p['_id'],'reservadas':0}); flash('Producto eliminado.','success')
    else: flash('No se puede eliminar un producto con reservas activas.','danger')
    return redirect(url_for('admin'))


@app.get('/ayuda')
def ayuda(): return render_template('ayuda.html')


@app.get('/api/productos')
def api_listar(): return jsonify([producto_publico(p) for p in productos.find()])


def api_admin():
    if not usuario_actual() or not usuario_actual().get('admin'): return jsonify(error='Se requiere sesión de administrador.'),403
    return None


@app.post('/api/productos')
def api_crear():
    err=api_admin()
    if err:return err
    try:
        data=validar_producto(request.get_json(silent=True) or {});data['reservadas']=0
        result=productos.insert_one(data); return jsonify(id=str(result.inserted_id)),201
    except ValueError as e: return jsonify(error=str(e)),400


@app.route('/api/productos/<id>',methods=['GET','PUT','DELETE'])
def api_item(id):
    p=productos.find_one({'_id':oid(id)})
    if not p: return jsonify(error='No encontrado'),404
    if request.method=='GET': return jsonify(producto_publico(p))
    err=api_admin()
    if err:return err
    if request.method=='DELETE':
        if p.get('reservadas',0): return jsonify(error='Hay reservas activas'),409
        result=productos.delete_one({'_id':p['_id'],'reservadas':0})
        return (jsonify(ok=True),200) if result.deleted_count else (jsonify(error='Conflicto'),409)
    try:
        data=validar_producto(request.get_json(silent=True) or {})
        result=productos.update_one({'_id':p['_id'],'reservadas':{'$lte':data['existencias']}},{'$set':data})
        if not result.matched_count:return jsonify(error='Stock menor que reservas'),409
        return jsonify(ok=True)
    except ValueError as e:return jsonify(error=str(e)),400


@app.get('/api/reservas/actual')
@login_required
def api_reserva_actual():
    r=reservas.find_one({'reserva_id':folio(),'usuario_id':oid(session['usuario_id']),'estado':'activa'})
    if not r:return jsonify(activa=False)
    return jsonify(activa=True,estado=r['estado'],vence_en=r['vence_en'].isoformat(),reserva_id=r['reserva_id'])


@app.errorhandler(403)
@app.errorhandler(404)
def error(e):return render_template('error.html',mensaje=str(e)),e.code


if __name__=='__main__':
    inicializar()
    app.run(debug=os.getenv('FLASK_DEBUG')=='1')

# Índices y compatibilidad de inventario al arrancar tanto local como con Gunicorn.
inicializar()
