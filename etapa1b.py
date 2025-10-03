#!/usr/bin/env python3
"""
Etapa 1B - Mapeamento de Localizações
======================================
Extrai GPS dos vídeos originais, faz reverse geocoding e gera imagens de lower third.
NÃO re-encoda vídeos - apenas mapeia e cria PNGs.
"""

import os
import json
import subprocess
import glob
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

# Importa configurações
try:
    import config
    GOOGLE_MAPS_API_KEY = getattr(config, 'GOOGLE_MAPS_API_KEY', None)
    USE_GOOGLE_MAPS = getattr(config, 'USE_GOOGLE_MAPS', False)
    GEOCODING_LANGUAGE = getattr(config, 'GEOCODING_LANGUAGE', 'pt-BR')
except ImportError:
    GOOGLE_MAPS_API_KEY = None
    USE_GOOGLE_MAPS = False
    GEOCODING_LANGUAGE = 'pt-BR'

# Tenta importar googlemaps
try:
    import googlemaps
    GOOGLEMAPS_AVAILABLE = True
except ImportError:
    GOOGLEMAPS_AVAILABLE = False
    if USE_GOOGLE_MAPS:
        print("⚠️ googlemaps não instalado. Execute: pip install googlemaps")
        print("⚠️ Usando Nominatim como fallback...")
        USE_GOOGLE_MAPS = False

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================

SOURCES_DIR = "sources"
OUTPUT_DIR = "output"
# LOCATIONS_MAP_FILE será gerado com timestamp no main()

# Extensões de vídeo suportadas
VIDEO_EXTENSIONS = ['*.mp4', '*.MP4', '*.avi', '*.mov', '*.mkv']

# Limitações
MAX_VIDEOS = 59

# Configurações de Lower Third
ACCENT_COLOR = (66, 133, 244, 255)  # Azul #4285F4
SUBTITLE_COLOR = (255, 255, 255, 255)  # Branco

# =============================================================================
# FUNÇÕES DE GPS E GEOCODING
# =============================================================================

def run_ffprobe_gps(file_path: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Executa ffprobe para extrair dados de GPS."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(file_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return None, f"Erro ffprobe: {result.stderr}"
        
        return json.loads(result.stdout), None
        
    except subprocess.TimeoutExpired:
        return None, "Timeout na execução do ffprobe"
    except json.JSONDecodeError:
        return None, "Erro ao decodificar JSON do ffprobe"
    except Exception as e:
        return None, f"Erro inesperado: {str(e)}"

def extract_gps_data(metadata: Dict) -> Dict:
    """Extrai dados de GPS dos metadados do ffprobe."""
    gps_data = {}
    
    if 'format' in metadata and 'tags' in metadata['format']:
        tags = metadata['format']['tags']
        gps_fields = {
            'location': ['location', 'com.apple.quicktime.location.ISO6709', 'GPS'],
            'latitude': ['latitude', 'com.apple.quicktime.location.latitude', 'GPS:Latitude'],
            'longitude': ['longitude', 'com.apple.quicktime.location.longitude', 'GPS:Longitude'],
            'timestamp': ['creation_time', 'com.apple.quicktime.creationdate', 'GPS:TimeStamp']
        }
        
        for field, possible_keys in gps_fields.items():
            for key in possible_keys:
                if key in tags:
                    gps_data[field] = tags[key]
                    break
    
    if 'streams' in metadata:
        for stream in metadata['streams']:
            if stream.get('codec_type') == 'video' and 'tags' in stream:
                tags = stream['tags']
                gps_fields = {
                    'location': ['location', 'com.apple.quicktime.location.ISO6709', 'GPS'],
                    'latitude': ['latitude', 'com.apple.quicktime.location.latitude', 'GPS:Latitude'],
                    'longitude': ['longitude', 'com.apple.quicktime.location.longitude', 'GPS:Longitude'],
                    'timestamp': ['creation_time', 'com.apple.quicktime.creationdate', 'GPS:TimeStamp']
                }
                for field, possible_keys in gps_fields.items():
                    if field not in gps_data:
                        for key in possible_keys:
                            if key in tags:
                                gps_data[field] = tags[key]
                                break
    
    return gps_data

def parse_gopro_location(location_str: str) -> Tuple[Optional[float], Optional[float]]:
    """Converte string de localização GoPro para coordenadas."""
    try:
        if not location_str or '/' not in location_str:
            return None, None
        
        coords = location_str.rstrip('/')
        import re
        match = re.match(r'^(-?\d+\.\d+)(-?\d+\.\d+)$', coords)
        
        if match:
            lat = float(match.group(1))
            lon = float(match.group(2))
            return lat, lon
    except:
        pass
    
    return None, None

def reverse_geocode_google_maps(lat: float, lon: float) -> Optional[str]:
    """Converte coordenadas GPS em endereço usando Google Maps API."""
    if not GOOGLEMAPS_AVAILABLE or not GOOGLE_MAPS_API_KEY:
        return None
    
    try:
        # Rate limit: Google Maps permite ~50 req/s, mas vamos ser conservadores
        # Adiciona delay de 0.1s entre requisições (10 req/s)
        time.sleep(0.1)
        
        # Inicializa cliente Google Maps
        gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
        
        # Faz geocoding reverso com retry
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Busca resultados (sem filtrar por tipo, aceita qualquer localização)
                results = gmaps.reverse_geocode(
                    (lat, lon),
                    language=GEOCODING_LANGUAGE
                )
                
                if results and len(results) > 0:
                    # Extrai componentes do endereço (mais confiável que formatted_address)
                    components = results[0].get('address_components', [])
                    
                    bairro = None
                    cidade = None
                    estado = None
                    
                    for component in components:
                        types = component.get('types', [])
                        name = component.get('long_name', '')
                        
                        # Bairro (sublocality_level_1 = bairro no Brasil)
                        if 'sublocality_level_1' in types or 'neighborhood' in types:
                            if not bairro:
                                bairro = name
                        
                        # Cidade
                        elif 'administrative_area_level_2' in types or 'locality' in types:
                            if not cidade:
                                cidade = name
                        
                        # Estado (usa short_name para sigla)
                        elif 'administrative_area_level_1' in types:
                            if not estado:
                                estado = component.get('short_name', name)
                    
                    # Monta o resultado: "Bairro | Cidade - Estado"
                    if bairro and cidade and estado:
                        return f"{bairro} | {cidade} - {estado}"
                    elif cidade and estado:
                        return f"{cidade} - {estado}"
                    elif bairro and cidade:
                        return f"{bairro} | {cidade}"
                    elif bairro:
                        return bairro
                    elif cidade:
                        return cidade
                    
                    # Fallback: formatted_address simplificado
                    address = results[0].get('formatted_address', '')
                    address = address.replace(', Brasil', '').replace(', Brazil', '')
                    import re
                    address = re.sub(r'\s*-?\s*\d{5}-?\d{3}\s*$', '', address)
                    return address.rstrip(',').strip() if address else None
                
                return None
                
            except Exception as e:
                error_msg = str(e)
                
                # Se for rate limit ou REQUEST_DENIED, tenta novamente com backoff exponencial
                if 'RATE_LIMIT' in error_msg or 'REQUEST_DENIED' in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Backoff exponencial: 1s, 2s, 4s
                        print(f"    ⏳ Rate limit atingido, aguardando {wait_time:.0f}s...")
                        time.sleep(wait_time)
                        continue
                
                # Outro erro, não tenta novamente
                raise e
        
        return None
        
    except Exception as e:
        print(f"    ⚠️ Erro Google Maps: {e}")
        return None

def reverse_geocode_nominatim(lat: float, lon: float) -> str:
    """Converte coordenadas GPS em endereço usando Nominatim (OpenStreetMap)."""
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': lat,
            'lon': lon,
            'format': 'json',
            'addressdetails': 1,
            'accept-language': GEOCODING_LANGUAGE
        }
        
        headers = {
            'User-Agent': 'FFmpegVideoProcessor/1.0 (Video GPS Analysis)'
        }
        
        # Respeita rate limit do Nominatim (1 req/sec)
        time.sleep(1.1)
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return format_address(data.get('address', {}))
        else:
            return f"Erro na API: {response.status_code}"
            
    except requests.exceptions.Timeout:
        return "Timeout na consulta"
    except requests.exceptions.RequestException as e:
        return f"Erro de rede: {str(e)}"
    except Exception as e:
        return f"Erro: {str(e)}"

def reverse_geocode(lat: float, lon: float) -> str:
    """Converte coordenadas GPS em endereço legível.
    
    Usa Google Maps API se configurado, senão usa Nominatim (OSM) como fallback.
    """
    # Tenta Google Maps primeiro se habilitado
    if USE_GOOGLE_MAPS and GOOGLE_MAPS_API_KEY and GOOGLEMAPS_AVAILABLE:
        address = reverse_geocode_google_maps(lat, lon)
        if address:
            return address
        print("    ⚠️ Google Maps falhou, usando Nominatim...")
    
    # Fallback para Nominatim
    return reverse_geocode_nominatim(lat, lon)

def format_address(address_data: Dict) -> str:
    """Formata dados de endereço em formato legível.
    
    Retorna no formato: "Bairro | Cidade - Estado"
    (Formato genérico para evitar erros de GPS impreciso da GoPro)
    """
    try:
        linha1 = None  # Bairro
        linha2_parts = []  # Cidade + Estado
        
        # LINHA 1: Bairro (mais confiável que rua/número com GPS impreciso)
        for key in ['suburb', 'neighbourhood', 'quarter', 'residential']:
            if key in address_data:
                linha1 = address_data[key]
                break
        
        # LINHA 2: Cidade + Estado
        # Cidade
        for key in ['city', 'town', 'village', 'municipality']:
            if key in address_data:
                linha2_parts.append(address_data[key])
                break
        
        # Estado (com hífen)
        if 'state' in address_data:
            state = address_data['state']
            # Lista completa de estados brasileiros com siglas
            states_map = {
                'São Paulo': 'SP', 'Rio de Janeiro': 'RJ', 'Minas Gerais': 'MG',
                'Bahia': 'BA', 'Paraná': 'PR', 'Rio Grande do Sul': 'RS',
                'Pernambuco': 'PE', 'Ceará': 'CE', 'Pará': 'PA', 'Goiás': 'GO',
                'Santa Catarina': 'SC', 'Espírito Santo': 'ES', 'Distrito Federal': 'DF',
                'Amazonas': 'AM', 'Mato Grosso': 'MT', 'Mato Grosso do Sul': 'MS',
                'Rondônia': 'RO', 'Acre': 'AC', 'Roraima': 'RR', 'Amapá': 'AP',
                'Tocantins': 'TO', 'Maranhão': 'MA', 'Piauí': 'PI', 'Alagoas': 'AL',
                'Sergipe': 'SE', 'Paraíba': 'PB', 'Rio Grande do Norte': 'RN'
            }
            state_abbr = states_map.get(state, state)
            
            # Adiciona com hífen se houver cidade
            if linha2_parts:
                linha2_parts[-1] = f"{linha2_parts[-1]} - {state_abbr}"
            else:
                linha2_parts.append(state_abbr)
        
        # Monta o resultado
        linha2 = ', '.join(linha2_parts) if linha2_parts else None
        
        if linha1 and linha2:
            return f"{linha1} | {linha2}"
        elif linha2:
            return linha2  # Só tem cidade/estado
        elif linha1:
            return linha1  # Só tem bairro
        
        # Fallback: tenta pegar algo útil do display_name
        display = address_data.get('display_name', '')
        if display:
            parts = [p.strip() for p in display.split(',')]
            # Tenta pegar primeiros elementos não vazios
            useful_parts = [p for p in parts[:3] if p]
            if len(useful_parts) >= 2:
                return f"{useful_parts[0]} | {useful_parts[1]}"
            elif useful_parts:
                return useful_parts[0]
        
        return "Localização não identificada"
        
    except Exception as e:
        return f"Erro ao formatar endereço: {str(e)}"

def get_video_dimensions(video_path: str) -> Tuple[int, int]:
    """Obtém dimensões do vídeo."""
    try:
        metadata, _ = run_ffprobe_gps(video_path)
        if metadata and 'streams' in metadata:
            for stream in metadata['streams']:
                if stream.get('codec_type') == 'video':
                    width = int(stream.get('width', 1920))
                    height = int(stream.get('height', 1080))
                    return width, height
    except:
        pass
    
    return 1920, 1080

# =============================================================================
# FUNÇÕES DE CRIAÇÃO DE LOWER THIRD
# =============================================================================

def pick_font(paths: List[str], size: int) -> ImageFont.ImageFont:
    """Seleciona fonte disponível."""
    for path in paths:
        try:
            return ImageFont.truetype(path, size=size)
        except:
            continue
    return ImageFont.load_default()

def split_location_for_title_subtitle(location_text: str) -> Tuple[str, str]:
    """Divide texto de localização em título e subtítulo.
    
    Formato esperado: "Bairro | Cidade - Estado"
    Retorna: ("BAIRRO", "Cidade - Estado")
    """
    # Primeiro tenta dividir pelo separador especial "|"
    if ' | ' in location_text:
        parts = location_text.split(' | ', 1)
        return parts[0].upper(), parts[1]  # Bairro em MAIÚSCULAS
    
    # Fallback: divide por vírgula ou hífen
    if ',' in location_text:
        parts = [p.strip() for p in location_text.split(",") if p.strip()]
        if len(parts) >= 2:
            return parts[0].upper(), ", ".join(parts[1:])
        elif len(parts) == 1:
            return parts[0].upper(), ""
    
    # Se tem hífen, tenta dividir (ex: "Cidade - Estado")
    if ' - ' in location_text:
        parts = location_text.split(' - ', 1)
        return parts[0].upper(), parts[1] if len(parts) > 1 else ""
    
    # Se não conseguiu dividir, retorna o texto original no título
    return location_text.upper(), ""

def create_lower_third_png(location_text: str, output_path: str, width: int, height: int) -> bool:
    """Cria PNG do lower third com pin."""
    try:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        WHITE = (255, 255, 255, 255)
        ACCENT = ACCENT_COLOR
        TXT_SUB = SUBTITLE_COLOR
        
        cx = width // 2
        baseline_y = int(height * 0.82)
        
        # Fontes
        title_font = pick_font([
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/calibrib.ttf"
        ], int(height * 0.055))
        
        subtitle_font = pick_font([
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/arial.ttf"
        ], int(height * 0.035))
        
        title, subtitle = split_location_for_title_subtitle(location_text)
        
        # PIN
        pin_h = int(height * 0.07)
        pin_r = int(pin_h * 0.38)
        pin_cy = baseline_y - int(height * 0.13)
        pin_cx = cx
        
        # Círculo externo
        draw.ellipse([pin_cx-pin_r, pin_cy-pin_r, pin_cx+pin_r, pin_cy+pin_r], fill=WHITE)
        
        # Círculo interno (transparente)
        inner_r = int(pin_r * 0.45)
        draw.ellipse([pin_cx-inner_r, pin_cy-inner_r, pin_cx+inner_r, pin_cy+inner_r], fill=(0, 0, 0, 0))
        
        # Triângulo
        tri_h = int(pin_h * 0.55)
        tri_w = int(pin_r * 1.1)
        draw.polygon([
            (pin_cx, pin_cy+pin_r+tri_h),
            (pin_cx-tri_w, pin_cy),
            (pin_cx+tri_w, pin_cy)
        ], fill=WHITE)
        
        # Linhas de destaque (azuis)
        line_y = pin_cy + pin_r + int(tri_h * 0.35)
        long_w = int(width * 0.08)
        short_w = int(width * 0.05)
        h_line = max(6, int(height * 0.003))
        
        draw.rectangle([cx-long_w//2, line_y, cx+long_w//2, line_y+h_line], fill=ACCENT)
        line_y2 = line_y + int(h_line * 2.5)
        draw.rectangle([cx-short_w//2, line_y2, cx+short_w//2, line_y2+h_line], fill=ACCENT)
        
        # Título
        try:
            draw.text((cx, baseline_y - int(height*0.03)), title, font=title_font, fill=WHITE, anchor="mm")
        except TypeError:
            tw, th = draw.textsize(title, font=title_font)
            draw.text((cx - tw//2, baseline_y - int(height*0.03) - th//2), title, font=title_font, fill=WHITE)
        
        # Pill com subtítulo
        if subtitle:
            pad_x = int(width * 0.015)
            pad_y = int(height * 0.008)
            
            try:
                sw = int(subtitle_font.getlength(subtitle))
                sh = subtitle_font.getbbox(subtitle)[3] - subtitle_font.getbbox(subtitle)[1]
            except Exception:
                sw, sh = draw.textsize(subtitle, font=subtitle_font)
            
            pill_w = sw + pad_x*2
            pill_h = sh + pad_y*2
            pill_r = pill_h // 2
            
            x1 = cx - pill_w//2
            y1 = baseline_y + int(height * 0.025)
            x2 = x1 + pill_w
            y2 = y1 + pill_h
            
            draw.rounded_rectangle([x1, y1, x2, y2], radius=pill_r, fill=ACCENT)
            
            try:
                draw.text((cx, y1 + pill_h//2), subtitle, font=subtitle_font, fill=TXT_SUB, anchor="mm")
            except TypeError:
                sww, shh = draw.textsize(subtitle, font=subtitle_font)
                draw.text((cx - sww//2, y1 + (pill_h - shh)//2), subtitle, font=subtitle_font, fill=TXT_SUB)
        
        img.save(output_path, "PNG")
        return True
        
    except Exception as e:
        print(f"    ❌ Erro ao criar PNG: {e}")
        return False

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def process_video_location(video_path: str, video_name: str) -> Optional[Dict]:
    """Processa localização de um vídeo e gera PNG do lower third."""
    print(f"\n  🔍 Processando: {video_name}")
    
    # 1. Extrai GPS
    metadata, error = run_ffprobe_gps(video_path)
    if error:
        print(f"    ⚠️ {error}")
        return None
    
    gps_data = extract_gps_data(metadata)
    if not gps_data:
        print("    ⚠️ Sem dados de GPS")
        return None
    
    # 2. Obtém coordenadas
    lat = lon = None
    
    if 'latitude' in gps_data and 'longitude' in gps_data:
        try:
            lat, lon = float(gps_data['latitude']), float(gps_data['longitude'])
        except:
            pass
    elif 'location' in gps_data:
        lat, lon = parse_gopro_location(gps_data['location'])
    
    if lat is None or lon is None:
        print("    ⚠️ Coordenadas GPS inválidas")
        return None
    
    print(f"    🌍 GPS: {lat:.4f}, {lon:.4f}")
    
    # 3. Reverse geocoding
    address = reverse_geocode(lat, lon)
    print(f"    🏠 Endereço: {address}")
    
    # 4. Obtém dimensões do vídeo
    width, height = get_video_dimensions(video_path)
    print(f"    📐 Dimensões: {width}x{height}")
    
    # 5. Gera PNG do lower third (com timestamp)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_filename = f"{timestamp}_lowerthird_{Path(video_name).stem}.png"
    png_path = os.path.join(OUTPUT_DIR, png_filename)
    
    if create_lower_third_png(address, png_path, width, height):
        print(f"    ✅ PNG criado: {png_filename}")
    else:
        print("    ❌ Falha ao criar PNG")
        return None
    
    # 6. Retorna dados
    return {
        "latitude": lat,
        "longitude": lon,
        "address": address,
        "png_path": png_path,
        "width": width,
        "height": height,
        "timestamp": gps_data.get('timestamp', '')
    }

def main():
    start_time = time.time()
    
    # Gera timestamp para os arquivos
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    locations_map_file = os.path.join(OUTPUT_DIR, f"{timestamp}_video_locations.json")
    
    print("📍 Etapa 1B - Mapeamento de Localizações")
    print("=" * 70)
    print("🎯 Objetivo: Mapear GPS e gerar imagens de lower third")
    print("⚡ SEM re-encodificação - apenas extração e criação de PNGs")
    
    # Mostra qual API está sendo usada
    if USE_GOOGLE_MAPS and GOOGLE_MAPS_API_KEY and GOOGLEMAPS_AVAILABLE:
        print("🗺️  Geocoding: Google Maps API ✅")
    else:
        print("🗺️  Geocoding: Nominatim (OpenStreetMap)")
        if USE_GOOGLE_MAPS and not GOOGLEMAPS_AVAILABLE:
            print("   ⚠️ googlemaps não instalado. Execute: pip install googlemaps")
    
    print("=" * 70)
    print()
    
    # Valida diretórios
    if not os.path.exists(SOURCES_DIR):
        print(f"❌ Diretório '{SOURCES_DIR}' não encontrado!")
        return
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Lista vídeos
    video_files = []
    for ext in VIDEO_EXTENSIONS:
        video_files.extend(glob.glob(os.path.join(SOURCES_DIR, ext)))
    video_files = list(set(video_files))
    video_files.sort()
    
    if not video_files:
        print(f"❌ Nenhum vídeo encontrado em '{SOURCES_DIR}'")
        return
    
    if len(video_files) > MAX_VIDEOS:
        print(f"⚠️  Encontrados {len(video_files)} vídeos, limitando a {MAX_VIDEOS}")
        video_files = video_files[:MAX_VIDEOS]
    
    print(f"📁 Diretório: {SOURCES_DIR}")
    print(f"🎬 Vídeos encontrados: {len(video_files)}")
    print()
    
    # Processa cada vídeo
    locations_map = {}
    processed_count = 0
    
    print("🔄 Processando vídeos...")
    
    for i, video_path in enumerate(video_files, 1):
        video_name = os.path.basename(video_path)
        print(f"\n[{i}/{len(video_files)}] {video_name}")
        
        location_data = process_video_location(video_path, video_name)
        
        if location_data:
            locations_map[video_name] = location_data
            processed_count += 1
    
    # Salva mapa de localizações
    print("\n" + "=" * 70)
    print(f"💾 Salvando mapa de localizações...")
    
    try:
        with open(locations_map_file, 'w', encoding='utf-8') as f:
            json.dump(locations_map, f, indent=2, ensure_ascii=False)
        print(f"✅ Mapa salvo: {locations_map_file}")
    except Exception as e:
        print(f"❌ Erro ao salvar mapa: {e}")
        return
    
    # Resumo
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("✅ Processamento concluído!")
    print(f"📊 Estatísticas:")
    print(f"   • Total de vídeos: {len(video_files)}")
    print(f"   • Com GPS: {processed_count}")
    print(f"   • Sem GPS: {len(video_files) - processed_count}")
    print(f"   • PNGs gerados: {processed_count}")
    print(f"⏱️  Tempo total: {total_time:.1f}s")
    print(f"📁 Mapa: {locations_map_file}")
    print()
    print("🎯 Próximo passo: Execute etapa2b para aplicar lower thirds no teaser")
    print("=" * 70)

if __name__ == "__main__":
    main()

