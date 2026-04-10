import psycopg2
from psycopg2.extras import execute_values
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def insertar_acta(conn, acta: dict) -> int:
    """Inserta el acta y devuelve su id. Si ya existe, devuelve el id existente."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO actas (acta_numero, fecha, participantes, hora_inicio, hora_fin, total_paginas)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (acta_numero) DO UPDATE SET
                fecha = EXCLUDED.fecha,
                participantes = EXCLUDED.participantes,
                hora_inicio = EXCLUDED.hora_inicio,
                hora_fin = EXCLUDED.hora_fin,
                total_paginas = EXCLUDED.total_paginas
            RETURNING id
        """, (
            acta["acta_numero"],
            acta.get("fecha"),
            acta.get("participantes", []),
            acta.get("hora_inicio"),
            acta.get("hora_fin"),
            acta.get("total_paginas")
        ))
        acta_id = cur.fetchone()[0]
    return acta_id

def insertar_nota(conn, nota: dict, acta_id: int, seccion_override: str = None) -> int:
    """Inserta una nota y devuelve su id"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO notas_ingresadas 
                (acta_id, codigo_nota, seccion, tema, fecha_nota, descripcion, resolucion)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            acta_id,
            nota.get("codigo_nota"),
            seccion_override or nota.get("seccion"),
            nota.get("tema"),
            nota.get("fecha_nota") or None,
            nota.get("descripcion"),
            nota.get("resolucion")
        ))
        nota_id = cur.fetchone()[0]
    
    # Inserta personas mencionadas
    personas = nota.get("personas", [])
    if personas:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO personas_mencionadas 
                    (nota_id, nombre_completo, numero_matricula, rol_mencion)
                VALUES %s
            """, [
                (nota_id, p.get("nombre_completo"), p.get("numero_matricula"), p.get("rol_mencion"))
                for p in personas
            ])
    
    # Inserta expedientes mencionados
    expedientes = nota.get("expedientes", [])
    if expedientes:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO expedientes_mencionados 
                    (nota_id, numero_expediente, referencia_ctd)
                VALUES %s
            """, [
                (nota_id, e.get("numero_expediente"), e.get("referencia_ctd"))
                for e in expedientes
            ])
    
    # Inserta resoluciones distritales
    resoluciones = nota.get("resoluciones_distritales", [])
    if resoluciones:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO resoluciones_distritales 
                    (nota_id, numero_resolucion, tecnico, matricula, tipo_resolucion, distrito)
                VALUES %s
            """, [
                (
                    nota_id,
                    r.get("numero_resolucion"),
                    r.get("tecnico"),
                    r.get("matricula"),
                    r.get("tipo_resolucion"),
                    r.get("distrito") or nota.get("seccion")
                )
                for r in resoluciones
            ])
    
    return nota_id

def insertar_temas_varios(conn, temas: list, acta_id: int):
    """Inserta los temas varios del acta"""
    if not temas:
        return
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO temas_varios 
                (acta_id, numero_punto, titulo, descripcion, resolucion)
            VALUES %s
        """, [
            (
                acta_id,
                t.get("numero_punto"),
                t.get("titulo"),
                t.get("descripcion"),
                t.get("resolucion")
            )
            for t in temas
        ])

def guardar_todo(datos: dict):
    """Inserta todos los datos extraídos en PostgreSQL de forma transaccional"""
    conn = get_connection()
    try:
        with conn:  # transaction
            acta_id = insertar_acta(conn, datos["acta"])
            print(f"[DB] Acta {datos['acta']['acta_numero']} → id {acta_id}")
            
            contador = 0
            for nota in datos["notas_me_mt"]:
                insertar_nota(conn, nota, acta_id)
                contador += 1
            
            for nota in datos["notas_distritos"]:
                insertar_nota(conn, nota, acta_id)
                contador += 1
            
            for nota in datos["notas_as"]:
                insertar_nota(conn, nota, acta_id)
                contador += 1
            
            for nota in datos["notas_at"]:
                insertar_nota(conn, nota, acta_id)
                contador += 1
            
            insertar_temas_varios(conn, datos["temas_varios"], acta_id)
            
            print(f"[DB] OK — {contador} notas insertadas, {len(datos['temas_varios'])} temas varios")
            return acta_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
