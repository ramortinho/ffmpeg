#!/usr/bin/env python3
"""
Programa para gerar arquivo final mesclando teaser com BGM + vídeo concatenado
Etapa 4: Criar versão final com teaser no início + vídeo completo
"""

import os
import subprocess
from pathlib import Path
from datetime import datetime
import time

# =============================================================================
# CONFIGURAÇÕES - ALTERE AQUI CONFORME NECESSÁRIO
# =============================================================================

# Diretórios
INPUT_DIR = "output"
OUTPUT_DIR = "output"

# Configurações de vídeo - ULTRA OTIMIZADO PARA 4K
# NOTA: Usando copy codec - SEM re-encodificação!

# =============================================================================

def validate_config():
    """Valida as configurações do programa"""
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Diretório de entrada '{INPUT_DIR}' não encontrado!")
        return False
    return True

def get_video_properties(video_path):
    """Obtém propriedades detalhadas do vídeo usando ffprobe"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', 
               '-show_format', '-show_streams', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except Exception as e:
        print(f"    ⚠️ Erro ao obter propriedades: {e}")
    return None

def get_video_duration(video_path):
    """Obtém duração do vídeo usando ffprobe"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
               '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    return None

def find_latest_teaser_with_bgm():
    """Encontra o teaser com BGM mais recente"""
    teaser_files = []
    for pattern in ['*teaser_with_bgm.mp4', '*teaser_with_bgm.MP4']:
        teaser_files.extend(Path(INPUT_DIR).glob(pattern))
    
    if not teaser_files:
        print(f"❌ Nenhum teaser com BGM encontrado na pasta '{INPUT_DIR}'")
        return None
    
    latest_teaser = max(teaser_files, key=lambda x: x.stat().st_mtime)
    print(f"    📁 Teaser com BGM selecionado: {latest_teaser.name}")
    return str(latest_teaser)

def find_latest_concatenated():
    """Encontra o vídeo concatenado mais recente"""
    video_files = []
    for pattern in ['*concatenated_videos.mp4', '*concatenated_videos.MP4']:
        video_files.extend(Path(INPUT_DIR).glob(pattern))
    
    if not video_files:
        print(f"❌ Nenhum vídeo concatenado encontrado na pasta '{INPUT_DIR}'")
        return None
    
    latest_video = max(video_files, key=lambda x: x.stat().st_mtime)
    print(f"    📁 Vídeo concatenado selecionado: {latest_video.name}")
    return str(latest_video)

def check_video_compatibility(teaser_path, concatenated_path):
    """Verifica se os vídeos são compatíveis para concatenação"""
    print("🔍 VERIFICANDO compatibilidade dos vídeos...")
    
    # Obter propriedades dos dois vídeos
    teaser_props = get_video_properties(teaser_path)
    concatenated_props = get_video_properties(concatenated_path)
    
    if not teaser_props or not concatenated_props:
        print("    ❌ Não foi possível obter propriedades dos vídeos")
        return False
    
    # Verificar streams de vídeo
    teaser_video_streams = [s for s in teaser_props.get('streams', []) if s.get('codec_type') == 'video']
    concatenated_video_streams = [s for s in concatenated_props.get('streams', []) if s.get('codec_type') == 'video']
    
    if not teaser_video_streams or not concatenated_video_streams:
        print("    ❌ Não foram encontrados streams de vídeo")
        return False
    
    # Verificar streams de áudio
    teaser_audio_streams = [s for s in teaser_props.get('streams', []) if s.get('codec_type') == 'audio']
    concatenated_audio_streams = [s for s in concatenated_props.get('streams', []) if s.get('codec_type') == 'audio']
    
    if not teaser_audio_streams or not concatenated_audio_streams:
        print("    ❌ Não foram encontrados streams de áudio")
        return False
    
    # Comparar propriedades críticas
    teaser_video = teaser_video_streams[0]
    concatenated_video = concatenated_video_streams[0]
    
    print(f"    📊 PROPRIEDADES DO TEASER:")
    print(f"      • Codec: {teaser_video.get('codec_name', 'N/A')}")
    print(f"      • Resolução: {teaser_video.get('width', 'N/A')}x{teaser_video.get('height', 'N/A')}")
    print(f"      • FPS: {teaser_video.get('r_frame_rate', 'N/A')}")
    print(f"      • Bitrate: {teaser_video.get('bit_rate', 'N/A')}")
    
    print(f"    📊 PROPRIEDADES DO VÍDEO CONCATENADO:")
    print(f"      • Codec: {concatenated_video.get('codec_name', 'N/A')}")
    print(f"      • Resolução: {concatenated_video.get('width', 'N/A')}x{concatenated_video.get('height', 'N/A')}")
    print(f"      • FPS: {concatenated_video.get('r_frame_rate', 'N/A')}")
    print(f"      • Bitrate: {concatenated_video.get('bit_rate', 'N/A')}")
    
    # Verificar compatibilidade
    compatible = True
    if teaser_video.get('codec_name') != concatenated_video.get('codec_name'):
        print(f"    ⚠️ Codecs diferentes: {teaser_video.get('codec_name')} vs {concatenated_video.get('codec_name')}")
        compatible = False
    
    if teaser_video.get('width') != concatenated_video.get('width') or teaser_video.get('height') != concatenated_video.get('height'):
        print(f"    ⚠️ Resoluções diferentes: {teaser_video.get('width')}x{teaser_video.get('height')} vs {concatenated_video.get('width')}x{concatenated_video.get('height')}")
        compatible = False
    
    if teaser_video.get('r_frame_rate') != concatenated_video.get('r_frame_rate'):
        print(f"    ⚠️ FPS diferentes: {teaser_video.get('r_frame_rate')} vs {concatenated_video.get('r_frame_rate')}")
        compatible = False
    
    if compatible:
        print("    ✅ Vídeos são compatíveis para concatenação!")
    else:
        print("    ⚠️ Vídeos têm propriedades diferentes - concat demuxer pode falhar")
    
    return compatible

def create_final_video(teaser_path, concatenated_path, output_path):
    """Cria vídeo final: teaser + vídeo concatenado"""
    print("🎬 Passo 2/2: CRIANDO vídeo final (teaser + vídeo completo)...")
    merge_start = time.time()
    
    # Verificar compatibilidade antes de prosseguir
    if not check_video_compatibility(teaser_path, concatenated_path):
        print("    ⚠️ Continuando mesmo com incompatibilidades...")
    
    # Obter durações para debug
    teaser_duration = get_video_duration(teaser_path)
    concatenated_duration = get_video_duration(concatenated_path)
    
    print(f"    🔍 DEBUG - Duração do teaser: {teaser_duration:.1f}s" if teaser_duration else "    🔍 DEBUG - Não foi possível obter duração do teaser")
    print(f"    🔍 DEBUG - Duração do vídeo concatenado: {concatenated_duration:.1f}s" if concatenated_duration else "    🔍 DEBUG - Não foi possível obter duração do vídeo concatenado")
    
    if teaser_duration and concatenated_duration:
        expected_duration = teaser_duration + concatenated_duration
        print(f"    🔍 DEBUG - Duração esperada do resultado: {expected_duration:.1f}s ({expected_duration/60:.1f} min)")
    
    # Criar arquivo de lista para concat demuxer
    list_file = os.path.join(OUTPUT_DIR, "final_video_list.txt")
    with open(list_file, 'w') as f:
        f.write(f"file '{os.path.abspath(teaser_path)}'\n")
        f.write(f"file '{os.path.abspath(concatenated_path)}'\n")
    
    # DEBUG: Mostrar conteúdo do arquivo de lista
    print(f"    🔍 DEBUG - Conteúdo do arquivo de lista:")
    with open(list_file, 'r') as f:
        for i, line in enumerate(f, 1):
            print(f"      {i}: {line.strip()}")
    
    # Comando FFmpeg para concatenar teaser + vídeo concatenado (SEM re-encodificação!)
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', list_file,
        '-c', 'copy',  # Apenas copy codec - SEM re-encodificação!
        '-avoid_negative_ts', 'make_zero',
        output_path
    ]
    
    print(f"    🔧 Mesclando teaser + vídeo completo...")
    print(f"    🔍 DEBUG - Comando: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # DEBUG: Mostrar stderr se houver
    if result.stderr:
        print(f"    🔍 DEBUG - FFmpeg stderr: {result.stderr}")
    
    # Limpar arquivo de lista
    if os.path.exists(list_file):
        os.remove(list_file)
    
    if result.returncode != 0:
        print(f"    ❌ Erro na mesclagem: {result.stderr}")
        return False
    
    # DEBUG: Verificar duração do arquivo final
    final_duration = get_video_duration(output_path)
    print(f"    🔍 DEBUG - Duração do arquivo final: {final_duration:.1f}s ({final_duration/60:.1f} min)" if final_duration else "    🔍 DEBUG - Não foi possível obter duração do arquivo final")
    
    if final_duration and teaser_duration and concatenated_duration:
        expected_duration = teaser_duration + concatenated_duration
        if abs(final_duration - expected_duration) > 1.0:  # Tolerância de 1 segundo
            print(f"    ⚠️ ATENÇÃO: Duração final ({final_duration:.1f}s) diferente da esperada ({expected_duration:.1f}s)")
        else:
            print(f"    ✅ Duração final correta!")
    
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
    
    print("🎬 ETAPA 4: Criação do Arquivo Final")
    print("⏱️  Resolução: ORIGINAL (4K) - SEM REDIMENSIONAMENTO")
    print("🔧 Codec: COPY - SEM re-encodificação!")
    print("🚀 ULTRA OTIMIZADO: Teaser + Vídeo Completo = Arquivo Final!")
    print("=" * 60)
    
    # Encontrar teaser com BGM mais recente
    teaser_path = find_latest_teaser_with_bgm()
    if not teaser_path:
        return
    
    print(f"📹 Teaser com BGM: {os.path.basename(teaser_path)}")
    
    # Encontrar vídeo concatenado mais recente
    concatenated_path = find_latest_concatenated()
    if not concatenated_path:
        return
    
    print(f"📹 Vídeo concatenado: {os.path.basename(concatenated_path)}")
    
    # Gerar nome do arquivo final
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{timestamp}_FINAL_teaser_plus_full_video.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # Criar vídeo final
    if not create_final_video(teaser_path, concatenated_path, output_path):
        print("❌ Erro ao criar arquivo final!")
        return
    
    # Resultado final
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("✅ ARQUIVO FINAL gerado com sucesso!")
    print(f"📁 Arquivo: {output_path}")
    print(f"🎬 Estrutura: Teaser com BGM + Vídeo Completo")
    print(f"⏱️  Tempo total: {format_time(total_time)}")
    
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"📊 Tamanho: {file_size:.2f} MB")
    
    print("\n🚀 OTIMIZAÇÕES APLICADAS:")
    print("   • CONCATENAÇÃO inteligente de teaser + vídeo completo")
    print("   • QUALIDADE 4K mantida")
    print("   • COPY CODEC - SEM re-encodificação!")
    print("   • ESTRUTURA: Teaser (com BGM) + Vídeo Original")

if __name__ == "__main__":
    main()