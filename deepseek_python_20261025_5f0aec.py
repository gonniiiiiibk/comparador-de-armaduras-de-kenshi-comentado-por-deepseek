"""
no_comment_main.py
==================
Analizador de armaduras de Kenshi.

Este programa carga la base de datos de armaduras definida en `armor_db`
(ver `no_comment_armor_db.py`) y ofrece las siguientes funcionalidades:

  1. Comparar todas las armaduras del juego, calculando tres índices:
       - armor_index : protección efectiva (resistencias × cobertura).
       - debuff_index: peso total de las penalizaciones.
       - bonus_index : peso total de los bonos.
  2. Ordenar y mostrar la tabla comparativa, destacando la mejor
     combinación de protección, penalizaciones y bonificaciones.
  3. Permitir el ingreso manual de armaduras para evaluarlas con la misma
     fórmula y compararlas entre sí.

NOTA: el import hace referencia a `armor_db`, que es el nombre con el que se
espera que esté disponible el módulo de base de datos (por ejemplo, renombrando
`no_comment_armor_db.py` a `armor_db.py`). Se mantiene tal cual para no alterar
el comportamiento original.
"""
from armor_db import (
    ARMADURAS_DB, PARTES_CUERPO, ETIQUETAS,
    STATS_PENALIZABLES, STATS_BONIFICABLES,
)


# =============================================================================
# UTILIDADES DE ENTRADA POR CONSOLA
# =============================================================================

def pedir_float(mensaje, minimo=0.0, maximo=1.0, permitir_vacio=False):
    """
    Solicita al usuario un número flotante por consola, validando rango.

    Args:
        mensaje (str): Texto que se muestra al pedir el valor.
        minimo (float): Valor mínimo aceptado (inclusive).
        maximo (float): Valor máximo aceptado (inclusive).
        permitir_vacio (bool): Si es True, la entrada vacía devuelve None.

    Returns:
        float | None: El número ingresado, o None si la entrada fue vacía y
        `permitir_vacio` era True.

    Comportamiento:
        - Reemplaza comas por puntos para aceptar notación decimal local.
        - Repite la pregunta hasta obtener un valor válido.
    """
    while True:
        # Se normaliza el separador decimal y se eliminan espacios.
        valor = input(mensaje).strip().replace(",", ".")
        if valor == "" and permitir_vacio:
            return None
        try:
            num = float(valor)
        except ValueError:
            print("  ⚠  Ingresa un número válido (ej: 0.75).")
            continue
        if num < minimo or num > maximo:
            print(f"  ⚠  El valor debe estar entre {minimo} y {maximo}.")
            continue
        return num


def pedir_texto(mensaje):
    """
    Solicita una cadena no vacía al usuario.

    Repite la pregunta hasta que se ingrese al menos un carácter distinto
    de espacios.

    Args:
        mensaje (str): Texto mostrado al pedir el valor.

    Returns:
        str: La cadena ingresada (con espacios exteriores recortados).
    """
    while True:
        txt = input(mensaje).strip()
        if txt:
            return txt
        print("  ⚠  Este campo no puede estar vacío.")


def pedir_si_no(mensaje):
    """
    Solicita una confirmación tipo sí/no.

    Acepta variantes en español e inglés: s, si, sí, y, yes / n, no.

    Args:
        mensaje (str): Texto mostrado al pedir la respuesta.

    Returns:
        bool: True para afirmativo, False para negativo.
    """
    while True:
        r = input(mensaje).strip().lower()
        if r in ("s", "si", "sí", "y", "yes"):
            return True
        if r in ("n", "no"):
            return False
        print("  ⚠  Responde 's' o 'n'.")


# =============================================================================
# NÚCLEO DE CÁLCULO
# =============================================================================

def evaluar_armadura(cut_res, blunt_res, harpoon_res, body_coverage,
                     penalizaciones, bonificaciones):
    """
    Calcula los tres índices agregados de una armadura a partir de sus
    estadísticas brutas.

    Fórmulas:
        armor_index  = promedio(cut, blunt, harpoon) × promedio(cobertura)
        debuff_index = sum(1 - mult  para cada penalización con mult < 1)
        bonus_index  = sum( (mult - 1)  si mult > 1   [bonos multiplicativos]
                          | (valor/10)  si valor <= 1 [bonos aditivos] )

    Args:
        cut_res (float): Resistencia a cortes.
        blunt_res (float): Resistencia a contundente.
        harpoon_res (float): Resistencia a arpones.
        body_coverage (dict): Cobertura por parte del cuerpo {parte: 0..1}.
        penalizaciones (dict): {stat: multiplicador <1}.
        bonificaciones (dict): {stat: valor >1 (mult) o <=1 (suma plana)}.

    Returns:
        dict: Índices redondeados a 4 decimales más promedios auxiliares.
    """
    # --- Cobertura promedio (0.0 si el dict está vacío) ---
    if body_coverage:
        cobertura_promedio = sum(body_coverage.values()) / len(body_coverage)
    else:
        cobertura_promedio = 0.0

    # --- Promedio simple de las tres resistencias (no ponderado) ---
    promedio_resistencias = (cut_res + blunt_res + harpoon_res) / 3

    # --- Índice de protección efectiva ---
    armor_index = promedio_resistencias * cobertura_promedio

    # --- Índice de penalización: cuánto reduce cada stat por debajo de 1 ---
    debuff_index = sum(1.0 - mult for mult in penalizaciones.values())
    debuff_index = max(0.0, debuff_index)  # Se acota a valores no negativos.

    # --- Índice de bonos: normaliza multiplicativos y aditivos a una escala ---
    bonus_total = 0.0
    for val in bonificaciones.values():
        if val > 1.0:
            # Bono multiplicativo: se toma la ganancia neta (val - 1).
            bonus_total += (val - 1.0)
        else:
            # Bono aditivo (o negativo): se divide por 10 como heurística para
            # llevarlo a una escala comparable a los multiplicativos.
            bonus_total += val / 10.0

    return {
        "armor_index":           round(armor_index, 4),
        "debuff_index":          round(debuff_index, 4),
        "bonus_index":           round(bonus_total, 4),
        "cobertura_promedio":    round(cobertura_promedio, 4),
        "promedio_resistencias": round(promedio_resistencias, 4),
    }


# =============================================================================
# COMPARATIVA GLOBAL (BASE DE DATOS)
# =============================================================================

def comparar_todas_las_armaduras():
    """
    Evalúa todas las armaduras de ARMADURAS_DB con `evaluar_armadura`, las
    ordena por `armor_index` descendente y muestra:

        - Una tabla comparativa completa.
        - La armadura con mejor equilibrio (armor - debuff + bonus).
        - Top 3 por índice de armadura puro.
        - Top 3 por índice de bonus.
    """
    # Encabezado decorativo de la sección.
    print("\n" + "=" * 100)
    print("  COMPARATIVA TOTAL DE ARMADURAS (Base de Datos - Grado Masterwork)")
    print("=" * 100)

    # --- Recolección de resultados ---
    resultados = []
    for nombre, datos in ARMADURAS_DB.items():
        # Se evalúa cada armadura con la misma fórmula que el ingreso manual.
        res = evaluar_armadura(
            cut_res=datos["cut_res"],
            blunt_res=datos["blunt_res"],
            harpoon_res=datos["harpoon_res"],
            body_coverage=datos["cobertura"],
            penalizaciones=datos["penalizaciones"],
            bonificaciones=datos["bonificaciones"],
        )

        # Se enriquecen los índices con metadatos de presentación.
        res["nombre"] = nombre
        res["slot"] = datos["slot"]
        res["clase"] = datos["clase"]
        resultados.append(res)

    # --- Ordenamiento por protección efectiva (mayor primero) ---
    resultados.sort(key=lambda x: x["armor_index"], reverse=True)

    # --- Tabla principal ---
    print(f"\n  {'Armadura':<24} {'Slot':<9} {'Clase':<8} "
          f"{'ArmorIdx':>10} {'DebuffIdx':>11} {'BonusIdx':>10}")
    print("  " + "-" * 96)

    for r in resultados:
        print(f"  {r['nombre']:<24} {r['slot']:<9} {r['clase']:<8} "
              f"{r['armor_index']:>10.4f} {r['debuff_index']:>11.4f} "
              f"{r['bonus_index']:>10.4f}")
    print("=" * 100)

    # --- Mejor equilibrio: protección - penalización + bono ---
    mejor = max(resultados,
                key=lambda x: x["armor_index"] - x["debuff_index"] + x["bonus_index"])
    print(f"\n  🏆 Mejor equilibrio (Armor - Debuff + Bonus): {mejor['nombre']}")
    print(f"     ArmorIdx={mejor['armor_index']:.4f} | "
          f"DebuffIdx={mejor['debuff_index']:.4f} | "
          f"BonusIdx={mejor['bonus_index']:.4f}")

    # --- Top 3 por índice de armadura puro ---
    print("\n  🛡️  Top 3 por Índice de Armadura puro:")
    for i, r in enumerate(resultados[:3], 1):
        print(f"     {i}. {r['nombre']} ({r['slot']}) → {r['armor_index']:.4f}")

    # --- Top 3 por índice de bonus ---
    top_bonus = sorted(resultados, key=lambda x: x["bonus_index"], reverse=True)[:3]
    print("\n  ✨ Top 3 por Índice de Bonus:")
    for i, r in enumerate(top_bonus, 1):
        print(f"     {i}. {r['nombre']} ({r['slot']}) → {r['bonus_index']:.4f}")


# =============================================================================
# INGRESO MANUAL DE ARMADURAS
# =============================================================================

def ingresar_armadura():
    """
    Guía al usuario para ingresar los datos de una armadura manualmente.

    Returns:
        dict: Datos de la armadura (resistencias, cobertura, penalizaciones,
              bonificaciones) junto con los tres índices calculados.

    El flujo es:
        1. Pedir nombre.
        2. Pedir las tres resistencias.
        3. Pedir la cobertura de cada parte del cuerpo.
        4. Pedir penalizaciones (solo se guardan las que tengan mult < 1).
        5. Pedir bonificaciones (solo se guardan las que sean ≠ 0).
        6. Llamar a `evaluar_armadura()` y devolver todo junto.
    """
    print("\n" + "=" * 55)
    print("  INGRESO MANUAL DE ARMADURA")
    print("=" * 55)

    # 1) Nombre identificatorio de la armadura.
    nombre = pedir_texto("Nombre: ")

    # 2) Resistencias individuales (rango 0.0 a 1.0).
    print("\n-- Resistencias (0.0 a 1.0) --")
    cut_res = pedir_float("  Resistencia a CORTES:       ")
    blunt_res = pedir_float("  Resistencia a CONTUNDENTE: ")
    harpoon_res = pedir_float("  Resistencia a ARPONES:     ")

    # 3) Cobertura por parte del cuerpo. Entrada vacía = 0.0.
    print("\n-- Cobertura por parte (0.0 a 1.0, vacío = 0) --")
    cobertura = {}
    for parte in PARTES_CUERPO:
        val = pedir_float(f"  {ETIQUETAS[parte]:<18}: ", permitir_vacio=True)
        cobertura[parte] = val if val is not None else 0.0

    # 4) Penalizaciones: solo se registran las que reducen (<1.0).
    print("\n-- PENALIZACIONES (multiplicador 0-1, vacío = sin penalización) --")
    penalizaciones = {}
    for stat in STATS_PENALIZABLES:
        val = pedir_float(f"  {stat:<22}: ", permitir_vacio=True)
        if val is not None and val < 1.0:
            penalizaciones[stat] = val

    # 5) Bonificaciones: solo se registran las distintas de cero.
    print("\n-- BONIFICACIONES (mult >1 o suma plana, vacío = sin bonus) --")
    bonificaciones = {}
    for stat in STATS_BONIFICABLES:
        val = pedir_float(f"  {stat:<22}: ", minimo=0.0, maximo=100.0,
                          permitir_vacio=True)
        if val is not None and val != 0:
            bonificaciones[stat] = val

    # 6) Cálculo de índices con la misma función que usa la base de datos.
    resultado = evaluar_armadura(cut_res, blunt_res, harpoon_res,
                                 cobertura, penalizaciones, bonificaciones)

    # Se devuelve un dict "plano" que mezcla los datos crudos con los índices.
    return {
        "nombre": nombre,
        "cut_res": cut_res, "blunt_res": blunt_res, "harpoon_res": harpoon_res,
        "cobertura": cobertura,
        "penalizaciones": penalizaciones,
        "bonificaciones": bonificaciones,
        **resultado,
    }


def mostrar_resultado(d):
    """
    Imprime en consola el desglose completo de una armadura ya evaluada.

    Muestra resistencias, cobertura (solo partes con valor > 0),
    penalizaciones, bonificaciones y los tres índices agregados dentro de
    un recuadro ASCII.

    Args:
        d (dict): Diccionario devuelto por `ingresar_armadura`.
    """
    print("\n" + "-" * 55)
    print(f"  RESULTADO: {d['nombre']}")
    print("-" * 55)

    # Resistencias expresadas en porcentaje.
    print(f"\n  Resistencias: Corte {d['cut_res']*100:.1f}% | "
          f"Contundente {d['blunt_res']*100:.1f}% | "
          f"Arpones {d['harpoon_res']*100:.1f}%")

    # Cobertura: se omiten las partes sin protección.
    print("\n  Cobertura:")
    for parte, val in d["cobertura"].items():
        if val > 0:
            print(f"    {ETIQUETAS[parte]:<18}: {val*100:5.1f}%")

    # Penalizaciones: se muestra el multiplicador y el porcentaje de pérdida.
    if d["penalizaciones"]:
        print("\n  Penalizaciones:")
        for stat, mult in d["penalizaciones"].items():
            print(f"    {stat:<22}: {mult:.2f}x ({(1-mult)*100:.1f}% menos)")

    # Bonificaciones: se distingue entre multiplicativas y aditivas.
    if d["bonificaciones"]:
        print("\n  Bonificaciones:")
        for stat, val in d["bonificaciones"].items():
            if val > 1.0:
                print(f"    {stat:<22}: {val:.2f}x (+{(val-1)*100:.1f}%)")
            else:
                print(f"    {stat:<22}: +{val:g}")

    # Recuadro final con los tres índices agregados.
    print("\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  ÍNDICE DE ARMADURA: {d['armor_index']:.4f}  ({d['armor_index']*100:.1f}%)  ║")
    print(f"  ║  ÍNDICE DE DEBUFF:   {d['debuff_index']:.4f}  ({d['debuff_index']*100:.1f}%)  ║")
    print(f"  ║  ÍNDICE DE BONUS:    {d['bonus_index']:.4f}                  ║")
    print("  ╚══════════════════════════════════════════╝")


def comparar_manuales(armaduras):
    """
    Imprime una tabla comparativa con las armaduras ingresadas manualmente.

    Args:
        armaduras (list[dict]): Lista de dicts devueltos por
            `ingresar_armadura`. Se ordena por `armor_index` descendente.
    """
    print("\n" + "=" * 85)
    print("  COMPARACIÓN DE ARMADURAS INGRESADAS MANUALMENTE")
    print("=" * 85)
    print(f"  {'Armadura':<24} {'ArmorIdx':>10} {'DebuffIdx':>12} {'BonusIdx':>10}")
    print("  " + "-" * 81)
    # Se recorre la lista ordenada por protección efectiva (mayor primero).
    for d in sorted(armaduras, key=lambda x: x["armor_index"], reverse=True):
        print(f"  {d['nombre']:<24} {d['armor_index']:>10.4f} "
              f"{d['debuff_index']:>12.4f} {d['bonus_index']:>10.4f}")
    print("=" * 85)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def main():
    """
    Orquesta el flujo completo del programa:

        1. Muestra el banner.
        2. Compara todas las armaduras de la base de datos.
        3. Pregunta si se desean ingresar armaduras manuales.
        4. Si sí, permite cargar N armaduras, mostrando el resultado de cada
           una y ofreciendo una comparativa final si hay más de una.
    """
    # Banner de bienvenida.
    print("╔═══════════════════════════════════════════════════╗")
    print("║   ANALIZADOR DE ARMADURAS DE KENSHI v4           ║")
    print("║   Base de datos integrada + comparativa total     ║")
    print("╚═══════════════════════════════════════════════════╝")

    # Fase 1: comparativa automática de la base de datos.
    comparar_todas_las_armaduras()

    # Fase 2: ingreso manual opcional de armaduras.
    print("\n" + "-" * 100)
    if pedir_si_no("¿Querés ingresar armaduras manualmente para comparar? (s/n): "):
        armaduras = []
        while True:
            # Se agrega una nueva armadura y se muestra su desglose.
            armaduras.append(ingresar_armadura())
            mostrar_resultado(armaduras[-1])
            # Se consulta si se desea seguir ingresando.
            if not pedir_si_no("\n¿Ingresar otra armadura? (s/n): "):
                break

        # La comparativa solo tiene sentido con más de una armadura.
        if len(armaduras) > 1:
            comparar_manuales(armaduras)

    print("\n¡Listo! Gracias por usar el analizador. 🛡️\n")


# Ejecuta `main` solo si el módulo se corre como script (no al importarse).
if __name__ == "__main__":
    main()