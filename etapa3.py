#!/usr/bin/env python3
"""
Programa para adicionar Background Music (BGM) ao teaser da etapa 2
Etapa 3: Verificar duração do teaser + selecionar BGM adequado + mesclar com -5dB
"""

import os
import subprocess
import json
from pathlib import Path
from datetime import datetime
import time

# =============================================================================
# CONFIGURAÇÕES - ALTERE AQUI CONFORME NECESSÁRIO
# =============================================================================

# Diretórios
INPUT_DIR = "output"
ASSETS_DIR = "assets"
OUTPUT_DIR = "output"

# Configurações de áudio
BGM_VOLUME_DB = -5  # Volume do BGM em dB (negativo = mais baixo que o áudio original)
AUDIO_CODEC = 'aac'
AUDIO_BITRATE = '128k'

# Configurações de vídeo - ULTRA OTIMIZADO PARA 4K
VIDEO_CODEC = 'copy'  # Manter codec original (hevc)
VIDEO_PRESET = None   # Não aplicável com copy
VIDEO_QUALITY = None  # Não aplicável com copy

# =============================================================================

def validate_config():
    """Valida as configurações do programa"""
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Diretório de entrada '{INPUT_DIR}' não encontrado!")
        return False
    
    if not os.path.exists(ASSETS_DIR):
        print(f"❌ Diretório de assets '{ASSETS_DIR}' não encontrado!")
        return False
    
    return True

def find_latest_teaser():
    """Encontra o teaser mais recente na pasta output"""
    # Buscar especificamente por arquivos teaser_sequential.mp4
    teaser_files = []
    for pattern in ['*teaser_sequential.mp4', '*teaser_sequential.MP4']:
        teaser_files.extend(Path(INPUT_DIR).glob(pattern))
    
    if not teaser_files:
        print(f"❌ Nenhum teaser encontrado na pasta '{INPUT_DIR}'")
        return None
    
    # Ordenar por data de modificação (mais recente primeiro)
    latest_teaser = max(teaser_files, key=lambda x: x.stat().st_mtime)
    print(f"    📁 Teaser selecionado: {latest_teaser.name}")
    return str(latest_teaser)

def get_audio_duration(file_path):
    """Obtém a duração de um arquivo de áudio/vídeo usando ffprobe"""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-show_entries', 'format=duration',
        '-of', 'csv=p=0',
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return float(result.stdout.strip())

def get_bgm_cache_path():
    """Gera caminho do cache de durações dos BGMs"""
    return os.path.join(ASSETS_DIR, "bgm_durations_cache.json")

def load_bgm_cache():
    """Carrega cache de durações dos BGMs se existir"""
    cache_path = get_bgm_cache_path()
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"      ⚠️ Erro ao carregar cache BGM: {e}")
    return {}

def save_bgm_cache(bgm_durations):
    """Salva cache de durações dos BGMs"""
    cache_path = get_bgm_cache_path()
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(bgm_durations, f, ensure_ascii=False, indent=2)
        print(f"      💾 Cache BGM salvo: {os.path.basename(cache_path)}")
    except Exception as e:
        print(f"      ⚠️ Erro ao salvar cache BGM: {e}")

def find_suitable_bgm(teaser_duration):
    """Encontra o BGM mais adequado (maior ou igual à duração do teaser)"""
    print(f"    🎵 Procurando BGM adequado para {teaser_duration:.1f}s...")
    
    # Carregar cache de durações
    bgm_cache = load_bgm_cache()
    
    # Buscar arquivos de áudio na pasta assets
    audio_extensions = ['*.mp3', '*.wav', '*.m4a', '*.aac', '*.ogg']
    audio_files = []
    
    for ext in audio_extensions:
        audio_files.extend(Path(ASSETS_DIR).glob(ext))
        audio_files.extend(Path(ASSETS_DIR).glob(ext.upper()))
    
    if not audio_files:
        print(f"    ❌ Nenhum arquivo de áudio encontrado na pasta '{ASSETS_DIR}'")
        return None
    
    print(f"    📁 Encontrados {len(audio_files)} arquivos de áudio")
    
    # Verificar duração de cada arquivo (usando cache quando possível)
    suitable_bgms = []
    cache_updated = False
    
    for audio_file in audio_files:
        file_path = str(audio_file)
        file_name = audio_file.name
        
        # Verificar se já está no cache
        if file_name in bgm_cache:
            duration = bgm_cache[file_name]
            print(f"      🎶 {file_name}: {duration:.1f}s (cache)")
        else:
            # Obter duração e salvar no cache
            duration = get_audio_duration(file_path)
            if duration is not None:
                bgm_cache[file_name] = duration
                cache_updated = True
                print(f"      🎶 {file_name}: {duration:.1f}s (novo)")
            else:
                continue
        
        if duration >= teaser_duration:
            suitable_bgms.append({
                'path': file_path,
                'name': file_name,
                'duration': duration
            })
    
    # Salvar cache atualizado se necessário
    if cache_updated:
        save_bgm_cache(bgm_cache)
    
    if not suitable_bgms:
        print(f"    ❌ Nenhum BGM encontrado com duração >= {teaser_duration:.1f}s")
        return None
    
    # Selecionar o BGM com duração mais próxima (menor ou igual)
    best_bgm = min(suitable_bgms, key=lambda x: x['duration'])
    
    print(f"    ✅ BGM selecionado: {best_bgm['name']} ({best_bgm['duration']:.1f}s)")
    return best_bgm

def add_bgm_to_teaser(teaser_path, bgm_path, output_path):
    """Adiciona BGM ao teaser com volume -5dB e fade out de 2 segundos"""
    print("🎵 Passo 2/2: MESCLANDO teaser com BGM + fade out...")
    merge_start = time.time()
    
    # Obter duração do teaser para calcular o fade out
    teaser_duration = get_audio_duration(teaser_path)
    if not teaser_duration:
        print("    ❌ Erro ao obter duração do teaser")
        return False
    
    fade_start = max(0, teaser_duration - 2.0)  # Fade out começa 2s antes do fim
    
    # ESTRATÉGIA: Primeiro mesclar áudio, depois combinar com vídeo
    temp_audio = output_path.replace('.mp4', '_temp_audio.aac')
    
    # Passo 1: Mesclar áudios
    cmd_audio = [
        'ffmpeg', '-y',
        '-i', teaser_path,
        '-i', bgm_path,
        '-filter_complex', f'[1:a]volume={BGM_VOLUME_DB}dB[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[audio_mixed];[audio_mixed]afade=t=out:st={fade_start:.1f}:d=2.0[audio]',
        '-map', '[audio]',
        '-c:a', 'aac',
        '-b:a', '128k',
        temp_audio
    ]
    
    print(f"    🔧 Passo 1/2: Mesclando áudios...")
    result1 = subprocess.run(cmd_audio, capture_output=True, text=True)
    
    if result1.returncode != 0:
        print(f"    ❌ Erro na mesclagem de áudio: {result1.stderr}")
        return False
    
    # Passo 2: Combinar vídeo original com áudio mesclado (SEM re-encodificação de vídeo!)
    cmd_video = [
        'ffmpeg', '-y',
        '-i', teaser_path,  # Vídeo original
        '-i', temp_audio,   # Áudio mesclado
        '-c:v', 'copy',     # Manter codec original (hevc) - SEM re-encodificação!
        '-c:a', 'copy',     # Copiar áudio mesclado
        '-map', '0:v',      # Vídeo do primeiro input
        '-map', '1:a',      # Áudio do segundo input
        '-shortest',
        output_path
    ]
    
    print(f"    🔧 Passo 2/2: Combinando vídeo + áudio mesclado...")
    result2 = subprocess.run(cmd_video, capture_output=True, text=True)
    
    # Limpar arquivo temporário
    if os.path.exists(temp_audio):
        os.remove(temp_audio)
    
    if result2.returncode != 0:
        print(f"    ❌ Erro na combinação vídeo+áudio: {result2.stderr}")
        return False
    
    merge_time = time.time() - merge_start
    print(f"✅ MESCLAGEM concluída em {format_time(merge_time)}")
    return True

def format_time(seconds):
    """Formata tempo em HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def main():
    start_time = time.time()
    
    # Validar configurações
    if not validate_config():
        return
    
    print("🎵 ETAPA 3: Adição de Background Music (BGM)")
    print("⏱️  Resolução: ORIGINAL (4K) - SEM REDIMENSIONAMENTO")
    print(f"🔧 Codec: COPY - SEM re-encodificação! | Áudio: {AUDIO_CODEC} | BGM: {BGM_VOLUME_DB}dB")
    print("🚀 ULTRA OTIMIZADO: Seleção automática de BGM + mesclagem inteligente!")
    print("=" * 60)
    
    # Encontrar teaser mais recente
    teaser_path = find_latest_teaser()
    if not teaser_path:
        return
    
    print(f"📹 Teaser encontrado: {os.path.basename(teaser_path)}")
    
    # Obter duração do teaser
    teaser_duration = get_audio_duration(teaser_path)
    if not teaser_duration:
        print("❌ Erro ao obter duração do teaser")
        return
    
    print(f"⏱️  Duração do teaser: {format_time(teaser_duration)}")
    
    # Encontrar BGM adequado
    bgm_info = find_suitable_bgm(teaser_duration)
    if not bgm_info:
        print("❌ Nenhum BGM adequado encontrado!")
        return
    
    # Gerar nome do arquivo final
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{timestamp}_teaser_with_bgm.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # Mesclar teaser com BGM
    if not add_bgm_to_teaser(teaser_path, bgm_info['path'], output_path):
        print("❌ Erro ao mesclar teaser com BGM!")
        return
    
    # Resultado final
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("✅ TEASER COM BGM gerado com sucesso!")
    print(f"📁 Arquivo: {output_path}")
    print(f"🎵 BGM usado: {bgm_info['name']} ({bgm_info['duration']:.1f}s)")
    print(f"🔊 Volume BGM: {BGM_VOLUME_DB}dB")
    print(f"⏱️  Tempo total: {format_time(total_time)}")
    
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"📊 Tamanho: {file_size:.2f} MB")
    
    print("\n🚀 OTIMIZAÇÕES APLICADAS:")
    print("   • SELEÇÃO automática de BGM adequado")
    print("   • MESCLAGEM inteligente com volume balanceado")
    print("   • QUALIDADE 4K mantida")
    print("   • CODEC otimizado para mesclagem de áudio")
    print("   • DURAÇÃO controlada (shortest)")

if __name__ == "__main__":
    main()
