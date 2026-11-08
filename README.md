# SOLESTYLE — Tienda de calzado con reservas temporales

Proyecto **nuevo e independiente**, creado desde cero. No contiene repositorio Git, cuenta de Atlas, credenciales, URL de Render ni administrador preconfigurados.

## Funciones

- Catálogo de calzado con talla, precio, categoría, imágenes opcionales y disponibilidad visible.
- Registro e inicio de sesión con contraseñas cifradas mediante hash.
- Administrador: crear, editar, eliminar y consultar productos (CRUD).
- Carrito de compras y pedidos **simulados**, sin cobros reales.
- API REST para Postman: `GET /api/productos`, `GET /api/productos/<id>`, `POST /api/productos`, `PUT /api/productos/<id>`, `DELETE /api/productos/<id>`; escrituras requieren iniciar sesión como administrador.
- Reservas de **5 minutos** (`300` segundos), consulta, confirmación, cancelación y vencimiento al acceder o recargar.
- Protección de inventario por actualización condicional atómica y **transacciones de MongoDB Atlas**; una segunda sesión no puede reservar la última unidad.
- Colecciones: `productos`, `usuarios`, `reservas`, `pedidos`.

## 1. Preparar el proyecto en Windows / VS Code

Abre la carpeta `SoleStyle_Calzado` en VS Code y abre PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita **solo `.env`** y coloca tus propios datos:

- `MONGO_URI`: cadena de conexión de **tu propio** clúster MongoDB Atlas.
- `MONGO_DB`: `solestyle_calzado` (puedes cambiarlo).
- `SECRET_KEY`: cadena aleatoria larga; puedes generar una con `python -c "import secrets; print(secrets.token_hex(32))"`.
- `ADMIN_EMAIL`: correo de tu administrador.
- `ADMIN_PASSWORD`: contraseña de tu administrador (mínimo 8 caracteres).

En Atlas crea usuario de base de datos con permisos de lectura/escritura, habilita acceso de red desde donde ejecutarás y desde Render, y utiliza un clúster que **admita transacciones** (Atlas replica set).

```powershell
python setup_admin.py
python seed_demo.py
python app.py
```

Abre `http://127.0.0.1:5000`. Para ingresar como administrador usa `ADMIN_EMAIL` y `ADMIN_PASSWORD`. `seed_demo.py` crea siete productos solo cuando el catálogo está vacío, incluido uno con **una sola unidad** para las pruebas.

**Importante:** no ejecutes `seed_demo.py` si no deseas productos de ejemplo. El administrador se crea al ejecutar `setup_admin.py`; el usuario común se registra desde la web.

## 2. Subir a tu propia cuenta de GitHub

```powershell
git init
git add .
git commit -m "Crear tienda de calzado SOLESTYLE"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

Crea primero un repositorio vacío en tu cuenta. Reemplaza `TU_USUARIO/TU_REPOSITORIO` por los tuyos. El archivo `.env` está excluido por `.gitignore`: **nunca lo subas**.

Para documentar la actividad en una rama independiente:

```powershell
git checkout -b reserva-temporal
git push -u origin reserva-temporal
```

El código ya incluye las reservas; la rama sirve para registrar la actividad sin modificar `main`. Para que Render despliegue esa rama, selecciónala en su configuración, o integra sus cambios en `main`.

## 3. Desplegar en tu propia cuenta de Render

1. New → Web Service → conecta **tu repositorio**.
2. Runtime: Python.
3. Build Command: `pip install -r requirements.txt`.
4. Start Command: `python setup_admin.py && gunicorn app:app`.
5. En Environment agrega `MONGO_URI`, `MONGO_DB`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` con **tus valores**.
6. Deploy y comprueba que el servicio esté Live. La primera ejecución creará/actualizará el administrador.
7. Para cargar los ejemplos en Atlas, ejecútalos localmente con la misma `MONGO_URI` mediante `python seed_demo.py`; no se cargan automáticamente en Render.

También se incluye `render.yaml` para Blueprint, pero puedes configurar el servicio manualmente. No hay cuentas ni servicios externos conectados en el ZIP.

## 4. Evidencias para el PDF del docente

Según **Actividad 2: adapta tu proyecto a una reserva temporal**, el recurso reservado es **cantidad de unidades de calzado**. El modelo es **cantidad**, con `existencias` y `reservadas`. La reserva incluye `reserva_id`, `recurso_id`, `cantidad`, `estado`, `creada_en` y `vence_en`.

1. Captura del catálogo con un modelo de **1 unidad disponible**.
2. Captura de la reserva activa y el **contador de 300 segundos**.
3. Captura del documento en Atlas (`reservas`): `reserva_id`, `recurso_id`, `cantidad`, `estado`, `creada_en`, `vence_en` (oculta datos personales).
4. Captura de **ventana normal (usuario A)** con la unidad reservada.
5. Captura de **ventana incógnito (usuario B)** con cero disponibles y mensaje de rechazo al reservar.
6. Captura de la cancelación y de la disponibilidad recuperada.
7. Nueva reserva: esperar cinco minutos, recargar y capturar el mensaje de vencimiento y el stock recuperado.
8. Nueva reserva: confirmar antes de cinco minutos, capturar **Mis compras** y verificar que la unidad ya no se libera.
9. Captura del repositorio GitHub, rama `reserva-temporal`, servicio Render Live y URL pública.
10. En portada: nombre del proyecto, integrantes, grado/grupo, enlace a GitHub y enlace a Render.

**Nota sobre el vencimiento:** la liberación se ejecuta al entrar/recargar la aplicación y en las operaciones; no existe un proceso de fondo permanente. La interfaz recarga al llegar a cero. La reserva vencida no puede confirmarse aunque un usuario manipule el contador.

## 5. Pruebas de Postman

`GET /api/productos` devuelve catálogo JSON sin autenticación. Para `POST`, `PUT`, `DELETE` inicia sesión como administrador en navegador o en Postman con cookie de sesión y utiliza JSON como:

```json
{"nombre":"Tenis de prueba","categoria":"Tenis","talla":"26","precio":999,"existencias":5,"descripcion":"Ejemplo","imagen":""}
```

`PUT` usa el mismo cuerpo completo. `DELETE` no elimina productos con unidades reservadas. No compartas cookies ni contraseñas.

## Estructura

```text
SoleStyle_Calzado/
├── app.py
├── setup_admin.py
├── seed_demo.py
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
├── templates/
├── static/styles.css
└── README.md
```

## Consideraciones

- Las reservas utilizan transacciones y escrituras condicionales para evitar sobreventa concurrente.
- El precio del pedido se guarda al reservar, evitando cambios posteriores del catálogo durante la reserva.
- Esta es una aplicación educativa de compras simuladas, **no** una pasarela de pagos.
- Las imágenes se cargan mediante URL externa opcional; no se guardan archivos en el disco efímero de Render.
- Para producción real, añade protección CSRF, limitación de intentos de login, auditoría y pruebas de carga.
