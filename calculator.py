"""
Módulo de cálculo de Expected Value (EV%) y desmargenado de cuotas.
"""
from typing import Tuple

def parse_percentage(val) -> float:
    """Convierte entradas como '5', '5%', '0.05', '5.5' a decimal (0.05)"""
    if isinstance(val, (int, float)):
        return float(val) / 100.0 if float(val) >= 1.0 else float(val)
    
    val_str = str(val).strip().replace("%", "").replace(",", ".")
    num = float(val_str)
    if num >= 1.0:
        return num / 100.0
    return num

def parse_odd(val) -> float:
    """Convierte entradas como '2.10', '2,10' a float"""
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace(",", ".")
    return float(val_str)

def calculate_ev(cuota_normal: float, cuota_aumentada: float, margen: float) -> Tuple[float, float]:
    """
    Calcula la probabilidad fair (desmargenada) y el porcentaje de Expected Value (EV%).
    
    Fórmula:
    - Margen m (en decimal, ej: 0.05 para 5%)
    - Probabilidad implícita en cuota normal = 1 / cuota_normal
    - Probabilidad fair = (1 / cuota_normal) / (1 + margen)
    - EV% = ((Probabilidad fair * cuota_aumentada) - 1) * 100
    
    Retorna:
    - ev_pct: float con el porcentaje de EV (ej: 7.42 para 7.42%)
    - prob_fair_pct: float con la probabilidad real estimada en %
    """
    cuota_n = parse_odd(cuota_normal)
    cuota_b = parse_odd(cuota_aumentada)
    m = parse_percentage(margen)
    
    if cuota_n <= 1.0 or cuota_b <= 1.0:
        raise ValueError("Las cuotas deben ser mayores que 1.0")
    
    # Probabilidad fair con margen eliminado (método multiplicativo habitual en value betting)
    prob_fair = (1.0 / cuota_n) / (1.0 + m)
    ev_decimal = (prob_fair * cuota_b) - 1.0
    ev_pct = ev_decimal * 100.0
    prob_fair_pct = prob_fair * 100.0
    
    return round(ev_pct, 2), round(prob_fair_pct, 2)
