import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import mysql.connector

# --- CONFIGURACIÓN 
URL_TIENDA = "http://books.toscrape.com/"
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'Admin',
    'database': 'libreria_db'
}

def convertir_rating_a_numero(rating_texto):
    mapeo_ratings = {
        "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5
    }
    return mapeo_ratings.get(rating_texto, None)

def extraer_descripcion(url_detalle):
    """Visita la página del libro y extrae su descripción (Scraping de profundidad)"""
    try:
        # Usamos un timeout corto para no ralentizar el proceso
        res = requests.get(url_detalle, timeout=10)
        sopa_detalle = BeautifulSoup(res.text, "lxml")
        
        # El sitio pone la descripción en el siguiente <p> después de un div con id 'product_description'
        header_desc = sopa_detalle.find("div", id="product_description")
        if header_desc:
            return header_desc.find_next("p").text.strip()
        return "Sin descripción disponible"
    except:
        return "Error al extraer descripción"

def limpiar_y_validar_libro(libro):
    try:
        nombre_libro = libro.h3.a['title'].strip()
        if not nombre_libro: return None
        
        precio_texto = libro.find('p', class_='price_color').text
        match_precio = re.search(r'\d+\.\d+', precio_texto)
        if not match_precio: return None
        
        precio_decimal = float(match_precio.group())
        if precio_decimal <= 0: return None
        
        estrellas_elem = libro.find('p', class_=re.compile("star-rating"))
        estrellas_texto = estrellas_elem['class'][1] if estrellas_elem else "No disponible"
        
        ratings_validos = ["One", "Two", "Three", "Four", "Five"]
        if estrellas_texto not in ratings_validos: return None
        
        estrellas = convertir_rating_a_numero(estrellas_texto)
        
        disponibilidad_elem = libro.find('p', class_='instock availability')
        disponibilidad = disponibilidad_elem.text.strip() if disponibilidad_elem else "Desconocido"
        
        # Extraemos la URL relativa y la convertimos en absoluta
        url_relativa = libro.h3.a['href'].replace("../../../", "catalogue/")
        if not url_relativa.startswith("catalogue/"):
            url_relativa = "catalogue/" + url_relativa
        url_absoluta = URL_TIENDA + url_relativa

        return {
            "titulo": nombre_libro,
            "precio": precio_decimal,
            "rating": estrellas,
            "disponibilidad": disponibilidad,
            "url": url_absoluta # La necesitamos para entrar al detalle
        }
    except Exception as error:
        print(f"  ❌ Error al procesar libro: {error}")
        return None

def ejecutar_scraping_completo():
    biblioteca_datos = []
    titulos_vistos = set()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for pagina_num in range(1, 4): 
        url = f"{URL_TIENDA}catalogue/page-{pagina_num}.html"
        print(f"📖 Procesando catálogo: Página {pagina_num}")
        
        try:
            respuesta = requests.get(url, headers=headers, timeout=10)
            sopa = BeautifulSoup(respuesta.text, "lxml")
            bloques_libros = sopa.find_all("article", class_=re.compile("product_pod"))
           
            for libro in bloques_libros:
    
                libro_limpio = limpiar_y_validar_libro(libro)             
            
                if libro_limpio is None or libro_limpio["titulo"] in titulos_vistos:
                    continue
                
                titulos_vistos.add(libro_limpio["titulo"])

                print(f"   🕵️  Extrayendo informacion libro: {libro_limpio['titulo'][:50]}...")
                libro_limpio["descripcion"] = extraer_descripcion(libro_limpio["url"])

                biblioteca_datos.append(libro_limpio)

                time.sleep(1)
            
        except Exception as error:
            print(f"❌ Error en página {pagina_num}: {error}")
    
    return biblioteca_datos

def persistir_datos(datos_extraidos):
    if not datos_extraidos: return
    
    df = pd.DataFrame(datos_extraidos)
    print("\n🔍 Validando datos antes de guardar...")
    
    # Guardar CSV (incluyendo descripción)
    df.to_csv("backup_libros.csv", index=False, encoding="utf-8-sig")
    print(f"💾 CSV guardado: backup_libros.csv")
    
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor()
        
       
        consulta_sql = "INSERT INTO libros (titulo, descripcion, precio, rating, disponibilidad) VALUES (%s, %s, %s, %s, %s)"
        valores = [(l['titulo'], l['descripcion'], l['precio'], l['rating'], l['disponibilidad']) for l in datos_extraidos]
        
        cursor.executemany(consulta_sql, valores)
        conexion.commit()
        print(f"✅ ÉXITO: {cursor.rowcount} libros guardados en MySQL con descripción")
        
    except mysql.connector.Error as err:
        print(f"❌ Error de base de datos: {err}")
    finally:
        if conexion.is_connected():
            conexion.close()

if __name__ == "__main__":
    print("="*60)
    print("🚀 Iniciando Pipeline de Datos (Etapa 3 CRISP-DM)")
    print("="*60)
    mis_libros = ejecutar_scraping_completo()
    if mis_libros:
        persistir_datos(mis_libros)