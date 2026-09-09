"""Tests de utilidades de limpieza y normalización del parser."""
from __future__ import annotations

from scripts.parsers.patterns.base import (
    DISTINGUIR_RE,
    clean_marca,
    clean_titular,
    extract_brand_lines,
    is_upperish,
    normalize_fecha,
    normalize_pais,
    parse_clase,
)


class TestDistingueMultilinea:
    def _grab(self, text):
        m = DISTINGUIR_RE.search(text)
        return m.group("distinguir").strip() if m else None

    def test_una_linea(self):
        assert self._grab("PARA DISTINGUIR: VEHÍCULOS Y AUTOMÓVILES") == (
            "VEHÍCULOS Y AUTOMÓVILES"
        )

    def test_multilinea(self):
        text = (
            "PARA DISTINGUIR: CONSTRUCCIÓN, REPARACIÓN Y\n"
            "MANTENIMIENTO DE MÁQUINAS Y HERRAMIENTAS\n"
            "SOLICITADA POR: X"
        )
        assert self._grab(text) == (
            "CONSTRUCCIÓN, REPARACIÓN Y\nMANTENIMIENTO DE MÁQUINAS Y HERRAMIENTAS"
        )

    def test_corta_en_linea_en_blanco(self):
        text = (
            "PARA DISTINGUIR: VEHÍCULOS\n"
            "\n"
            "Insc. 2026-0001 del 1 DE ENERO DE 2026"
        )
        assert self._grab(text) == "VEHÍCULOS"

    def test_corta_en_siguiente_insc(self):
        text = (
            "PARA DISTINGUIR: ACCESORIOS Y PARTES PARA AUTOMÓVILES\n"
            "Insc. 2026-0002 del 2 DE ENERO DE 2026"
        )
        assert self._grab(text) == "ACCESORIOS Y PARTES PARA AUTOMÓVILES"

    def test_corta_en_campo_siguiente(self):
        text = (
            "PARA DISTINGUIR: ROPA Y CALZADO\n"
            "DOMICILIO: CARACAS\n"
            "EN CLASE: 25"
        )
        assert self._grab(text) == "ROPA Y CALZADO"


class TestCleanMarca:
    def test_quita_prefijo_h(self):
        assert clean_marca("H PIMACO") == "PIMACO"

    def test_quita_prefijo_n(self):
        assert clean_marca("N SERVICENOW") == "SERVICENOW"

    def test_quita_prefijo_e(self):
        assert clean_marca("E LA GEAR") == "LA GEAR"

    def test_quita_prefijo_c(self):
        assert clean_marca("C FRESH FOOD") == "FRESH FOOD"

    def test_quita_prefijo_z(self):
        assert clean_marca("Z MARCA") == "MARCA"

    def test_preserva_caracteres_especiales(self):
        # copyright
        assert clean_marca("MILL©S PRIDE") == "MILL©S PRIDE"

    def test_preserva_apostrofe(self):
        assert clean_marca("NATY´S") == "NATY´S"

    def test_preserva_punto(self):
        assert clean_marca("WEB.COM") == "WEB.COM"

    def test_preserva_numeros(self):
        assert clean_marca("TOTALPEDIDOS.COM") == "TOTALPEDIDOS.COM"

    def test_quita_traduccion_parentesis(self):
        # Si tiene paréntesis al final, se queda con el nombre principal.
        result = clean_marca("EXTREMEN FLOTATION (FLOTACIÓN EXTREMA)")
        assert result == "EXTREMEN FLOTATION"

    def test_none_devuelve_none(self):
        assert clean_marca(None) is None

    def test_string_vacio_devuelve_vacio(self):
        assert clean_marca("") == ""


class TestCleanTitular:
    def test_corta_en_domicilio(self):
        s = "MILKAUT S.A Domicilio: ARGENTINA,BUENOS AIRES"
        assert clean_titular(s) == "MILKAUT S.A"

    def test_corta_en_pais(self):
        s = "ACME HOLDINGS LLC País: VENEZUELA"
        assert clean_titular(s) == "ACME HOLDINGS LLC"

    def test_corta_en_tramitante(self):
        s = "ACME S.A.\nTRAMITANTE: ALGUIEN"
        assert clean_titular(s) == "ACME S.A"

    def test_none_devuelve_none(self):
        assert clean_titular(None) is None


class TestNormalizePais:
    def test_palabras_pegadas(self):
        # "ESTADOS UNIDOSDEAMÉRICA" → "ESTADOS UNIDOS DE AMÉRICA"
        assert normalize_pais("ESTADOS UNIDOSDEAMÉRICA") == "ESTADOS UNIDOS DE AMÉRICA"

    def test_pais_simple(self):
        assert normalize_pais("VENEZUELA") == "VENEZUELA"

    def test_quita_cid_residual(self):
        assert normalize_pais("ESTADOS(cid:38) UNIDOS") == "ESTADOS UNIDOS"

    def test_none_devuelve_none(self):
        assert normalize_pais(None) is None


class TestNormalizeFecha:
    def test_formato_completo(self):
        assert normalize_fecha("30 DE OCTUBRE DE 2015") == "2015-10-30"

    def test_minusculas(self):
        assert normalize_fecha("15 de febrero de 2026") == "2026-02-15"

    def test_setiembre_como_septiembre(self):
        assert normalize_fecha("01 DE SETIEMBRE DE 2025") == "2025-09-01"

    def test_formato_irreconocible(self):
        assert normalize_fecha("not a date") is None

    def test_mes_invalido(self):
        assert normalize_fecha("01 DE MESINVALIDO DE 2025") is None

    def test_dia_fuera_de_rango(self):
        # Día 32 es inválido
        assert normalize_fecha("32 DE ENERO DE 2025") is None

    def test_none(self):
        assert normalize_fecha(None) is None


class TestParseClase:
    def test_clase_numerica_valida(self):
        n, lc = parse_clase("30")
        assert n == 30
        assert lc is None

    def test_clase_lc(self):
        n, lc = parse_clase("LC")
        assert n is None
        assert lc == "LC"

    def test_clase_minuscula(self):
        n, lc = parse_clase("lc")
        assert n is None
        assert lc == "LC"

    def test_clase_fuera_de_rango(self):
        n, lc = parse_clase("50")
        assert n is None
        assert lc is None

    def test_none(self):
        assert parse_clase(None) == (None, None)


class TestIsUpperish:
    def test_todo_mayusculas(self):
        assert is_upperish("PIMACO")

    def test_mayusculas_con_espacios(self):
        assert is_upperish("UCAMAY CALM RESTORE")

    def test_minusculas(self):
        assert not is_upperish("minúsculas")

    def test_mezclado(self):
        # "Web.Com" tiene 2 mayúsculas y 4 minúsculas
        assert not is_upperish("Web.Com", threshold=0.7)

    def test_con_caracteres_especiales(self):
        assert is_upperish("MILL©S PRIDE")

    def test_vacio(self):
        assert not is_upperish("")


class TestExtractBrandLines:
    def test_una_linea_mayuscula(self):
        text = "TRIPLE MILLONARIO\nEN CLASE: 35\nPARA DISTINGUIR: ..."
        lines = extract_brand_lines(text)
        assert lines == ["TRIPLE MILLONARIO"]

    def test_multiples_lineas(self):
        text = (
            "CUANDO PIENSES EN CABLES\n"
            "PIENSA EN CABLESCA\n"
            "EN CLASE: 9"
        )
        lines = extract_brand_lines(text)
        assert lines == ["CUANDO PIENSES EN CABLES", "PIENSA EN CABLESCA"]

    def test_corta_en_linea_no_mayuscula(self):
        text = "TRIPLE MILLONARIO\nPara distinguir: ..."
        lines = extract_brand_lines(text)
        assert lines == ["TRIPLE MILLONARIO"]

    def test_corta_en_EN_CLASE(self):
        text = "EN CLASE: 35\nTRIPLE MILLONARIO"
        lines = extract_brand_lines(text, end=text.find("EN CLASE"))
        assert lines == []

    def test_ignora_domicilio_pais(self):
        text = "DOMICILIO: CARACAS\nPAÍS: VENEZUELA\nEN CLASE: 25"
        lines = extract_brand_lines(text)
        assert lines == []


class TestDisposicionesAdministrativas:
    """Pattern D: resoluciones de la sección DISPOSICIONES ADMINISTRATIVAS.

    Los ejemplos replican la estructura real del BPI 654 (tomos XVII y
    XVIII): preámbulo ministerial, tabla N°/SOLICITUD/MARCA/CLASE/
    SOLICITANTE con líneas separadas y fórmula "RESUELVE" al final.
    """

    @staticmethod
    def _resolucion_confirmacion() -> str:
        return (
            "CARACAS, 26 DE MAYO DE 2026\n"
            "216°, 167° y 27°\n"
            "RESOLUCIÓN Nº\n"
            "Vistos los recursos de reconsideración interpuestos conforme a lo\n"
            "dispuesto en el artículo 94 de la Ley Orgánica de Procedimientos\n"
            "Administrativos, contra las Resoluciones No. 1087, 126, 306, 401 y 879;\n"
            "que negaron los siguientes signos por encontrarse incursos en las\n"
            "causales prohibitivas contenidas en la Ley de Propiedad Industrial:\n"
            "N°\n"
            "SOLICITUD\n"
            "MARCA\n"
            "CLASE\n"
            "SOLICITANTE\n"
            "1.\n"
            "1994-010804\n"
            "GLOBO\n"
            "38 INT\n"
            "TV GLOBO LTDA\n"
            "2.\n"
            "2010-015133\n"
            "PUROSOYA\n"
            "29 INT\n"
            "A.B. INVERSIONES, C.A.\n"
            "Ahora bien, de la revisión exhaustiva de los documentos que reposan en\n"
            "los expedientes administrativos se evidencia que no consta poder.\n"
            "En virtud de las consideraciones que anteceden, este Despacho resuelve:\n"
            "RESUELVE\n"
            "Conforme a lo dispuesto en los artículos 86 y 49 numeral 6 de la Ley\n"
            "Orgánica de Procedimientos Administrativos, este Registro decide:\n"
            "1.- INADMISIBLE los escritos interpuestos.\n"
            "2.- CONFIRMA las Resoluciones No. 1087, 126, 306, 401 y 879.\n"
            "Comuníquese y Publíquese.\n"
        )

    @staticmethod
    def _resolucion_concesion() -> str:
        return (
            "CARACAS, 29 DE MAYO DE 2026\n"
            "RESOLUCIÓN Nº\n"
            "Vistos los recursos de reconsideración interpuestos contra las\n"
            "Resoluciones No. 128, 807 y 177; que negaron los siguientes signos:\n"
            "N°\n"
            "SOLICITUD\n"
            "MARCA\n"
            "CLASE\n"
            "SOLICITANTE\n"
            "1.\n"
            "2017-001123\n"
            "(GRÁFICA)\n"
            "39 INT\n"
            "CORPORACION MEGALIMENTOS 2011, C.A.\n"
            "2.\n"
            "2012-014434\n"
            "MONSTER\n"
            "REHAB\n"
            "5 INT\n"
            "MONSTER ENERGY COMPANY\n"
            "RESUELVE\n"
            "Este Registro de la Propiedad Industrial, decide:\n"
            "1. Declarar CON LUGAR los Recursos de Reconsideración interpuestos.\n"
            "2. REVOCAR las Resoluciones No. 128, 807 y 177.\n"
            "3. CONCEDER los signos a favor de sus actuales solicitantes.\n"
            "La parte interesada debe cargar en el sistema en línea WEBPI el pago\n"
            "de los montos correspondientes en un lapso de treinta (30) días\n"
            "hábiles, contados a partir de la entrada en vigencia del Boletín.\n"
        )

    def test_extrae_solicitudes_con_marca_y_tipo(self):
        from scripts.parsers.patterns.disposiciones import extract

        out = list(extract(self._resolucion_confirmacion()))
        exps = {e["expediente"] for e in out}
        assert exps == {"1994-010804", "2010-015133"}
        by_exp = {e["expediente"]: e for e in out}
        assert by_exp["1994-010804"]["marca"] == "GLOBO"
        assert by_exp["1994-010804"]["clase_niza"] == 38
        assert by_exp["1994-010804"]["titular"] == "TV GLOBO LTDA"
        assert by_exp["2010-015133"]["titular"] == "A.B. INVERSIONES, C.A."
        # La decisión confirma resoluciones que negaron → NEGACION.
        assert by_exp["1994-010804"]["tipo_disposicion"] == "NEGACION"
        assert "RESUELVE" in by_exp["1994-010804"]["disposicion"]
        assert all(e["matcheable"] for e in out)

    def test_resolucion_concesion_precede_a_revoca(self):
        from scripts.parsers.patterns.disposiciones import extract

        out = list(extract(self._resolucion_concesion()))
        by_exp = {e["expediente"]: e for e in out}
        assert {"2017-001123", "2012-014434"} == set(by_exp)
        # Efecto neto: se conceden los signos (no la revocación previa).
        assert by_exp["2012-014434"]["tipo_disposicion"] == "CONCESION"
        # Marca de dos líneas se une; clase con INT se parsea.
        assert by_exp["2012-014434"]["marca"] == "MONSTER REHAB"
        assert by_exp["2012-014434"]["clase_niza"] == 5
        assert by_exp["2017-001123"]["marca"] == "(GRÁFICA)"
        assert by_exp["2017-001123"]["titular"] == "CORPORACION MEGALIMENTOS 2011, C.A."

    def test_resolucion_caducidad(self):
        from scripts.parsers.patterns.disposiciones import extract

        text = (
            "CARACAS, 1 DE JUNIO DE 2026\n"
            "RESOLUCIÓN Nº\n"
            "Vistos la solicitud de caducidad por no uso contra el registro\n"
            "de la marca siguiente:\n"
            "1.\n"
            "2011-012345\n"
            "KEEWAY MOTOR\n"
            "12 INT\n"
            "QIANJIANG-KEEWAY IPARI\n"
            "RESUELVE\n"
            "PRIMERO: este Registro declara la caducidad del registro marcario.\n"
        )
        out = list(extract(text))
        assert len(out) == 1
        assert out[0]["tipo_disposicion"] == "CADUCA"

    def test_nombre_marca_con_resolucion_prefix_no_es_bloque(self):
        """Marcas que empiezan con 'RESOLUCIÓN...' en otras secciones no
        generan entradas (no hay preámbulo ministerial)."""
        from scripts.parsers.patterns.disposiciones import extract

        text = (
            "Insc. 2020-009999 del 5 DE ABRIL DE 2020\n"
            "SOLICITADA POR: TALLERES SL País: VENEZUELA\n"
            "RESOLUCIÓN DE CONFLICTOS. ELABORACIÓN DE OPINIONES LEGALES\n"
            "EN CLASE: 35\n"
            "PARA DISTINGUIR: CONSULTORÍA.\n"
        )
        assert list(extract(text)) == []

    def test_resolucion_sin_solicitudes_no_emite_nada(self):
        from scripts.parsers.patterns.disposiciones import extract

        text = (
            "CARACAS, 3 DE JULIO DE 2026\n"
            "RESOLUCIÓN Nº\n"
            "Vistos lo anterior, se aprueba el informe de gestión 2025.\n"
            "RESUELVE\n"
            "Aprobar el informe de gestión.\n"
        )
        assert list(extract(text)) == []

    def test_integracion_parser_completo(self):
        """El parser completo (A→B→C→D) incorpora las entradas de
        disposiciones y no rompe las de otras secciones."""
        from scripts.parsers.marca_entry import MarcaEntryParser

        text = (
            "--- página 85 ---\n"
            "MARCAS CON ORDEN DE PUBLICACIÓN\n"
            "Insc. 2026-001001 del 1 DE MAYO DE 2026\n"
            "SOLICITADA POR: ACME SA País: VENEZUELA\n"
            "ACME ROJA\n"
            "EN CLASE: 5\n"
            "PARA DISTINGUIR: FARMACOS.\n"
            + self._resolucion_confirmacion()
        )
        entries = MarcaEntryParser().parse(text)
        by_exp = {e.expediente: e for e in entries}
        assert by_exp["2026-001001"].marca == "ACME ROJA"
        assert by_exp["1994-010804"].marca == "GLOBO"
        assert by_exp["1994-010804"].fuente_parsing == "disposiciones"
        assert by_exp["1994-010804"].tipo_disposicion == "NEGACION"

    def test_resolucion_devueltas_de_forma(self):
        """Formato real BPI 654 pág. 958: clase antes de la marca, 'NC'
        sin clase, titular con prosa 'Domicilio:' y columna TRAMITANTE."""
        from scripts.parsers.patterns.disposiciones import extract

        text = (
            "Caracas, 01 de junio de 2026\n"
            "RESOLUCIÓN N°\n"
            "DEVUELTAS DE FORMA\n"
            "VISTAS LAS SOLICITUDES DE MARCAS COMERCIALES, QUE A CONTINUACIÓN SE\n"
            "ESPECIFICAN, Y POR CUANTO LOS INTERESADOS NO CUMPLIERON CON LOS\n"
            "REQUISITOS FORMALES DE PRESENTACIÓN, SE DEVUELVEN DICHAS SOLICITUDES\n"
            "A FIN DE QUE SE DÉ CUMPLIMIENTO A LO EXIGIDO DENTRO DE UN LAPSO DE\n"
            "TREINTA (30) DÍAS HÁBILES CONTADOS A PARTIR DE LA FECHA DE LA\n"
            "PUBLICACIÓN DEL PRESENTE BOLETÍN.\n"
            "SOLICITUD\n"
            "CLASE\n"
            "NOMBRE DE LAS MARCAS\n"
            "TITULAR\n"
            "TRAMITANTE\n"
            "2016-017396\n"
            "36\n"
            "SOFITEL CENTRO DE ATENCION TELEFONICO\n"
            "BANCO SOFITASA BANCO UNIVERSAL,\n"
            "C.A. (BANCO SOFITASA, C.A.) Domicilio:\n"
            "SAN CRISTOBAL - EDO. TACHIRA País:\n"
            "VENEZUELA\n"
            "CARRASCOSA DE MENA JOSE MANUEL\n"
            "2016-017764\n"
            "NC\n"
            "MACUTO\n"
            "CENTRO COMERCIAL MACUTO I, C.A.\n"
            "Domicilio: Maracay Estado Aragua País:\n"
            "VENEZUELA\n"
            "EDUARDO C. DIAZ SANTOS\n"
        )
        out = {e["expediente"]: e for e in extract(text)}
        assert set(out) == {"2016-017396", "2016-017764"}
        # Tipo por marcador de sección del bloque, no por la decisión.
        assert all(e["tipo_disposicion"] == "DEVOLUCION_FORMA" for e in out.values())
        assert out["2016-017396"]["marca"] == "SOFITEL CENTRO DE ATENCION TELEFONICO"
        assert out["2016-017396"]["clase_niza"] == 36
        assert out["2016-017764"]["marca"] == "MACUTO"
        assert out["2016-017764"]["clase_niza"] is None
        # Titular best-effort: se corta en la prosa del domicilio.
        assert out["2016-017764"]["titular"] == "CENTRO COMERCIAL MACUTO I, C.A."
