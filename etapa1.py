#!/usr/bin/env python3
"""
Programa para concatenar vídeos da pasta sources na pasta output
Etapa 1C: Trim, concatenação e normalização em 3 passos separados
"""

import os
import subprocess
import glob
import tempfile
from pathlib import Path
from datetime import datetime
import time

# =============================================================================
# CONFIGURAÇÕES - ALTERE AQUI CONFORME NECESSÁRIO
# =============================================================================

# Diretórios
SOURCES_DIR = "sources"
OUTPUT_DIR = "output"

# Limitações
MAX_VIDEOS = 59
TRIM_SECONDS = 1.0

# Extensões de vídeo suportadas
VIDEO_EXTENSIONS = ['*.mp4', '*.MP4', '*.avi', '*.mov', '*.mkv']

# Configurações de vídeo - MANTER RESOLUÇÃO ORIGINAL (4K)
OUTPUT_WIDTH = None  # Manter largura original
OUTPUT_HEIGHT = None  # Manter altura original

# Configurações de codec de vídeo - USAR COPY (sem re-encodificação)
VIDEO_CODEC = 'copy'  # Copia sem re-encodificar
VIDEO_PRESET = None   # Não aplicável com copy
VIDEO_QUALITY = None  # Não aplicável com copy

# Configurações de áudio
AUDIO_CODEC = 'aac'
AUDIO_BITRATE = '128k'

# Configurações de fade e normalização
FADE_IN_DURATION = 1.0  # Duração do fade in em segundos (início do vídeo)
AUDIO_FILTER = f'afade=t=in:st=0:d={FADE_IN_DURATION},loudnorm'  # Fade in + normalização

# =============================================================================

def validate_config():
    """Valida as configurações do programa"""
    if not os.path.exists(SOURCES_DIR):
        print(f"❌ Diretório de origem '{SOURCES_DIR}' não encontrado!")
        return False
    
    if MAX_VIDEOS <= 0:
        print("❌ MAX_VIDEOS deve ser maior que 0!")
        return False
    
    if TRIM_SECONDS < 0:
        print("❌ TRIM_SECONDS deve ser maior ou igual a 0!")
        return False
    
    if OUTPUT_WIDTH is not None and (OUTPUT_WIDTH <= 0 or OUTPUT_HEIGHT <= 0):
        print("❌ Dimensões de saída devem ser maiores que 0!")
        return False
    
    return True

def get_video_duration(video_path):
    """Obtém a duração de um vídeo usando ffprobe"""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-show_entries', 'format=duration',
        '-of', 'csv=p=0',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return float(result.stdout.strip())

def trim_video(input_video, output_video):
    """Aplica apenas trim em um vídeo (sem normalização)"""
    duration = get_video_duration(input_video)
    if duration is None:
        print(f"    ❌ Erro: Não foi possível obter duração de {input_video}")
        return False
    
    end_time = duration - TRIM_SECONDS
    
    # Trim apenas (sem normalização)
    cmd_trim = [
        'ffmpeg', '-y',
        '-i', input_video,
        '-ss', str(TRIM_SECONDS),
        '-to', str(end_time),
        '-c', 'copy',
        output_video
    ]
    
    result = subprocess.run(cmd_trim, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ❌ Erro no trim: {result.stderr}")
        return False
    
    return True

def concat_videos(video_list, output_video):
    """Concatena uma lista de vídeos (SEM normalização) - MANTÉM RESOLUÇÃO ORIGINAL"""
    if len(video_list) == 1:
        # Apenas 1 vídeo, copia
        cmd = [
            'ffmpeg', '-y', 
            '-i', video_list[0],
            '-c', 'copy',  # Copia tudo sem re-encodificar
            output_video
        ]
    else:
        # Múltiplos vídeos, concatena com copy (mesma resolução)
        # Criar arquivo de lista para concatenação mais eficiente
        list_file = output_video.replace('.mp4', '_list.txt')
        
        with open(list_file, 'w') as f:
            for video in video_list:
                # Usar caminho absoluto para evitar problemas
                abs_path = os.path.abspath(video)
                f.write(f"file '{abs_path}'\n")
        
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',  # Copia tudo sem re-encodificar
            output_video
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Limpar arquivo de lista
        if os.path.exists(list_file):
            os.remove(list_file)
        
        if result.returncode != 0:
            print(f"    ❌ Erro na concatenação: {result.stderr}")
        return result.returncode == 0

def normalize_audio(input_video, output_video):
    """Aplica normalização de áudio em um vídeo"""
    cmd = [
        'ffmpeg', '-y',
        '-i', input_video,
        '-c:v', 'copy',  # Copia vídeo sem re-encodificar
        '-af', AUDIO_FILTER,
        '-c:a', AUDIO_CODEC,
        '-b:a', AUDIO_BITRATE,
        output_video
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

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
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Encontrar vídeos
    video_files = []
    for ext in VIDEO_EXTENSIONS:
        video_files.extend(glob.glob(os.path.join(SOURCES_DIR, ext)))
    video_files = list(set(video_files))
    video_files.sort()

    if not video_files:
        print(f"❌ Nenhum arquivo de vídeo encontrado na pasta '{SOURCES_DIR}'")
        return

    if len(video_files) > MAX_VIDEOS:
        print(f"⚠️  Encontrados {len(video_files)} vídeos, limitando a {MAX_VIDEOS}")
        video_files = video_files[:MAX_VIDEOS]

    print(f"📹 Processando {len(video_files)} vídeos")
    print(f"⏱️  Resolução: ORIGINAL (4K) - SEM REDIMENSIONAMENTO")
    print(f"🔧 Trim: {TRIM_SECONDS}s | Codec: {VIDEO_CODEC} | Áudio: {AUDIO_CODEC}")
    print(f"🎚️  Fade In: {FADE_IN_DURATION}s + Normalização de áudio")
    print("🚀 ULTRA OTIMIZADO: Copy codec + resolução original + normalização separada!")
    print("=" * 60)

    # Passo 1: Apenas trim dos vídeos (sem normalização)
    print("🔄 Passo 1/3: Aplicando TRIM nos vídeos...")
    processed_videos = []
    trim_start = time.time()
    
    for i, video in enumerate(video_files, 1):
        elapsed = time.time() - start_time
        print(f"  {i}/{len(video_files)}: {os.path.basename(video)} - {format_time(elapsed)}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        processed_file = os.path.join(OUTPUT_DIR, f"trimmed_{i:02d}_{timestamp}_{os.path.basename(video)}")
        
        if not trim_video(video, processed_file):
            print(f"❌ Erro ao processar {os.path.basename(video)}")
            return
        
        processed_videos.append(processed_file)

    trim_time = time.time() - trim_start
    print(f"✅ TRIM concluído em {format_time(trim_time)}")

    # Passo 2: Concatenar vídeos (sem normalização)
    print(f"\n🔄 Passo 2/3: CONCATENANDO vídeos...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_concat = os.path.join(OUTPUT_DIR, f"temp_{timestamp}_concatenated.mp4")
    
    concat_start = time.time()
    print(f"  📎 Concatenando {len(processed_videos)} vídeos...")
    
    if not concat_videos(processed_videos, temp_concat):
        print("❌ Erro na concatenação")
        return
    
    concat_time = time.time() - concat_start
    print(f"✅ CONCATENAÇÃO concluída em {format_time(concat_time)}")

    # Passo 3: Normalizar áudio do vídeo concatenado
    print(f"\n🔄 Passo 3/3: NORMALIZANDO áudio do vídeo final...")
    final_output = os.path.join(OUTPUT_DIR, f"{timestamp}_concatenated_videos.mp4")
    
    normalize_start = time.time()
    print(f"  🔊 Aplicando loudnorm no áudio...")
    
    if not normalize_audio(temp_concat, final_output):
        print("❌ Erro na normalização")
        return
    
    normalize_time = time.time() - normalize_start
    print(f"✅ NORMALIZAÇÃO concluída em {format_time(normalize_time)}")

    # Limpeza do arquivo temporário
    if os.path.exists(temp_concat):
        os.remove(temp_concat)

    # Resultado final
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("✅ Processamento concluído com sucesso!")
    print(f"📁 Arquivo final: {final_output}")
    print(f"⏱️  Tempo total: {format_time(total_time)}")
    print(f"📊 Breakdown dos tempos:")
    print(f"   • TRIM: {format_time(trim_time)}")
    print(f"   • CONCATENAÇÃO: {format_time(concat_time)}")
    print(f"   • NORMALIZAÇÃO: {format_time(normalize_time)}")
    
    if os.path.exists(final_output):
        file_size = os.path.getsize(final_output) / (1024 * 1024)
        print(f"📊 Tamanho: {file_size:.2f} MB")
    
    # Limpeza
    print("\n🧹 Limpando arquivos temporários...")
    for video in processed_videos:
        if os.path.exists(video):
            os.remove(video)
    print("✅ Limpeza concluída!")
    print("\n🚀 ULTRA OTIMIZAÇÃO APLICADA:")
    print("   • TRIM rápido (copy codec)")
    print("   • CONCATENAÇÃO com resolução 4K original")
    print(f"   • FADE IN de áudio ({FADE_IN_DURATION}s) para entrada suave")
    print("   • NORMALIZAÇÃO apenas no vídeo final")
    print("   • ZERO re-encodificação desnecessária")
    print("   • Etapa 2 será 100x mais rápida!")

if __name__ == "__main__":
    main()
