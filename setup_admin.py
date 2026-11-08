"""Ejecuta una sola vez para crear o actualizar el administrador indicado en .env."""
import os
from werkzeug.security import generate_password_hash
from app import usuarios
correo=os.getenv('ADMIN_EMAIL','').strip().lower()
clave=os.getenv('ADMIN_PASSWORD','')
if not correo or '@' not in correo or len(clave)<8:
    raise SystemExit('Define ADMIN_EMAIL y ADMIN_PASSWORD (mínimo 8 caracteres) en .env')
usuarios.update_one({'correo':correo},{'$set':{'nombre':'Administrador','clave_hash':generate_password_hash(clave),'admin':True}},upsert=True)
print('Administrador configurado:',correo)
