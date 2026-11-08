"""Carga catálogo de muestra solo si la colección está vacía."""
from app import productos
muestra=[
 ('Urban Street','Tenis','26',1299,8),('Runner Pro','Deportivo','27',1599,12),
 ('Classic Canvas','Casual','25',899,15),('Chelsea Night','Botas','26',1899,5),
 ('Elegance Oxford','Formal','28',1799,6),('Summer Walk','Sandalias','24',699,10),
 ('Edición Limitada','Tenis','27',2299,1)]
if productos.count_documents({})==0:
    productos.insert_many([dict(nombre=n,categoria=c,talla=t,precio=p,existencias=s,reservadas=0,descripcion='Calzado de demostración para el catálogo SOLESTYLE.',imagen='') for n,c,t,p,s in muestra])
    print('Catálogo de demostración creado. Incluye una unidad para prueba de concurrencia.')
else: print('Ya hay productos: no se modificó el catálogo.')
