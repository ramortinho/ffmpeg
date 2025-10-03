#!/usr/bin/env python3
"""
Etapa 2B - Aplicação de Lower Thirds no Teaser
==============================================
Aplica lower thirds com base em GPS nos clipes do teaser gerado pela etapa 2.
Re-encoda mantendo HEVC para compatibilidade com etapa 4.
"""

import os
import json
import subprocess
import glob
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================

SOURCES_DIR = "sources"
OUTPUT_DIR = "output"

# Extensões de vídeo
VIDEO_EXTENSIONS = ['*.mp4', '*.MP4', '*.avi', '*.mov', '*.mkv']

# Configurações de Lower Third
OVERLAY_FADE_IN = 0.5   # Fade in de 0.5s
OVERLAY_DURATION = 4.0  # Duração total do lower third
# Sem fade out - cut direto

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def find_latest_file(pattern: str) -> Optional[str]:
    """Encontra o arquivo mais recente que corresponde ao padrão."""
    files = glob.glob(os.path.join(OUTPUT_DIR, pattern))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def get_video_duration(video_path: str) -> Optional[float]:
    """Obtém a duração de um vídeo usando ffprobe."""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except Exception as e:
        print(f"    ❌ Erro ao obter duração: {e}")
        return None

def check_nvenc_support() -> bool:
    """Verifica se NVENC (NVIDIA) está disponível."""
    try:
        cmd = ['ffmpeg', '-hide_banner', '-encoders']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return 'hevc_nvenc' in result.stdout or 'h264_nvenc' in result.stdout
    except:
        return False

def get_video_properties(video_path: str) -> Dict:
    """Obtém propriedades do vídeo (codec, resolução, fps, bitrate)."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return {}
        
        data = json.loads(result.stdout)
        props = {}
        
        # Propriedades do vídeo
        if 'streams' in data:
            for stream in data['streams']:
                if stream.get('codec_type') == 'video':
                    props['codec'] = stream.get('codec_name', 'hevc')
                    props['width'] = int(stream.get('width', 1920))
                    props['height'] = int(stream.get('height', 1080))
                    props['fps'] = eval(stream.get('r_frame_rate', '30/1'))
                    props['pix_fmt'] = stream.get('pix_fmt', 'yuv420p')
                    break
        
        # Bitrate
        if 'format' in data:
            props['bitrate'] = int(data['format'].get('bit_rate', 0))
        
        return props
        
    except Exception as e:
        print(f"    ❌ Erro ao obter propriedades: {e}")
        return {}

def format_time(seconds: float) -> str:
    """Formata tempo em HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# =============================================================================
# MAPEAMENTO DE VÍDEOS
# =============================================================================

def build_video_timeline(sources_dir: str) -> List[Dict]:
    """Constrói timeline dos vídeos originais com timestamps acumulados."""
    # Lista vídeos originais
    video_files = []
    for ext in VIDEO_EXTENSIONS:
        video_files.extend(glob.glob(os.path.join(sources_dir, ext)))
    video_files = list(set(video_files))
    video_files.sort()
    
    if not video_files:
        return []
    
    timeline = []
    accumulated_time = 0.0
    
    for video_path in video_files:
        video_name = os.path.basename(video_path)
        duration = get_video_duration(video_path)
        
        if duration is None:
            print(f"    ⚠️ Não foi possível obter duração de {video_name}")
            continue
        
        timeline.append({
            'video_name': video_name,
            'video_path': video_path,
            'start_time': accumulated_time,
            'end_time': accumulated_time + duration,
            'duration': duration
        })
        
        accumulated_time += duration
    
    return timeline

def find_video_for_timestamp(timeline: List[Dict], timestamp: float) -> Optional[str]:
    """Encontra qual vídeo original contém um determinado timestamp."""
    for video_info in timeline:
        if video_info['start_time'] <= timestamp < video_info['end_time']:
            return video_info['video_name']
    
    # Último vídeo (edge case)
    if timeline and timestamp >= timeline[-1]['start_time']:
        return timeline[-1]['video_name']
    
    return None

# =============================================================================
# PROCESSAMENTO DO TEASER
# =============================================================================

def map_teaser_clips_to_videos(
    transcript_data: Dict,
    gpt_response: str,
    timeline: List[Dict],
    locations_data: Dict
) -> List[Dict]:
    """Mapeia clipes do teaser para vídeos originais e lower thirds."""
    
    # Parse dos IDs selecionados pelo GPT
    try:
        selected_ids = [int(x.strip()) for x in gpt_response.split(',') if x.strip().isdigit()]
    except:
        print("    ❌ Erro ao parsear IDs do GPT")
        return []
    
    segments = transcript_data.get('segments', [])
    clips_mapping = []
    
    accumulated_duration = 0.0
    
    for segment_id in selected_ids:
        # Usa o ID como índice do array (GPT retorna índices 0-N)
        if segment_id < 0 or segment_id >= len(segments):
            print(f"      ⚠️ Segmento ID {segment_id} fora do range (0-{len(segments)-1})")
            continue
        
        segment = segments[segment_id]
        
        start_in_concat = segment['start']
        end_in_concat = segment['end']
        duration = end_in_concat - start_in_concat
        
        # Encontra qual vídeo original contém este segmento
        video_name = find_video_for_timestamp(timeline, start_in_concat)
        
        if not video_name:
            print(f"      ⚠️ Segmento ID {segment_id} @ {start_in_concat:.1f}s: vídeo não encontrado na timeline")
            accumulated_duration += duration
            continue
        
        # Verifica se este vídeo tem lower third disponível
        has_lower_third = video_name in locations_data
        lower_third_png = None
        
        if has_lower_third:
            lower_third_png = locations_data[video_name].get('png_path')
        
        clips_mapping.append({
            'segment_id': segment_id,
            'start_in_concat': start_in_concat,
            'end_in_concat': end_in_concat,
            'duration': duration,
            'start_in_teaser': accumulated_duration,
            'end_in_teaser': accumulated_duration + duration,
            'video_name': video_name,
            'has_lower_third': has_lower_third,
            'lower_third_png': lower_third_png
        })
        
        accumulated_duration += duration
    
    return clips_mapping

def apply_lower_thirds_to_teaser(
    teaser_path: str,
    clips_mapping: List[Dict],
    output_path: str
) -> bool:
    """Aplica lower thirds no teaser com fade in e cut out usando NVENC se disponível."""
    
    print(f"\n🎨 Aplicando lower thirds no teaser...")
    print(f"📁 Teaser: {os.path.basename(teaser_path)}")
    print(f"📊 Clipes com lower third: {sum(1 for c in clips_mapping if c['has_lower_third'])}")
    
    # Obtém propriedades do teaser
    props = get_video_properties(teaser_path)
    
    if not props:
        print("    ❌ Não foi possível obter propriedades do teaser")
        return False
    
    # Filtra apenas clipes com lower third
    clips_with_lt = [c for c in clips_mapping if c['has_lower_third']]
    
    if not clips_with_lt:
        print("    ⚠️ Nenhum clipe tem lower third disponível")
        # Copia o teaser original
        import shutil
        shutil.copy2(teaser_path, output_path)
        return True
    
    # Verifica suporte NVENC
    has_nvenc = check_nvenc_support()
    if has_nvenc:
        print("    🎮 GPU NVIDIA detectada - usando NVENC para acelerar!")
    else:
        print("    💻 Usando CPU (NVENC não disponível)")
    
    # Monta comando FFmpeg baseado no exemplo da etapa8c.py
    # Cada overlay é aplicado individualmente com fade
    
    print(f"\n🎬 Processando {len(clips_with_lt)} lower thirds...")
    
    # Vamos aplicar os overlays um por vez para garantir que funcionem
    current_input = teaser_path
    temp_outputs = []
    
    for idx, clip in enumerate(clips_with_lt):
        if not clip['lower_third_png'] or not os.path.exists(clip['lower_third_png']):
            print(f"    ⚠️ PNG não encontrado para clipe {idx+1}")
            continue
        
        start_time = clip['start_in_teaser']
        end_time = min(start_time + OVERLAY_DURATION, clip['end_in_teaser'])
        duration = end_time - start_time
        
        print(f"    🎨 Aplicando lower third {idx+1}/{len(clips_with_lt)}...")
        print(f"        📍 Posição: {start_time:.1f}s-{end_time:.1f}s ({duration:.1f}s)")
        print(f"        🖼️  PNG: {os.path.basename(clip['lower_third_png'])}")
        
        # Determina output (último overlay vai para output_path final)
        if idx == len(clips_with_lt) - 1:
            current_output = output_path
        else:
            temp_out = os.path.join(OUTPUT_DIR, f"temp_overlay_{idx}.mp4")
            temp_outputs.append(temp_out)
            current_output = temp_out
        
        # Filtro complexo: PNG com fade + overlay
        filter_complex = (
            f"[1:v]format=rgba,"
            f"fade=t=in:st=0:d={OVERLAY_FADE_IN}:alpha=1[ov];"
            f"[0:v][ov]overlay=0:0:enable='between(t,{start_time},{end_time})'"
        )
        
        # Configurações de encode
        codec = props.get('codec', 'hevc')
        bitrate = props.get('bitrate', 0)
        
        if has_nvenc and (codec == 'hevc' or codec == 'h265'):
            # NVENC HEVC (muito mais rápido!)
            encode_args = [
                '-c:v', 'hevc_nvenc',
                '-preset', 'p4',  # p1-p7, p4 = balanced
                '-rc', 'vbr',
                '-cq', '23',
                '-b:v', '0'
            ]
            if bitrate > 0:
                encode_args.extend(['-maxrate', str(bitrate), '-bufsize', str(bitrate * 2)])
        elif has_nvenc:
            # NVENC H.264 (fallback)
            encode_args = [
                '-c:v', 'h264_nvenc',
                '-preset', 'p4',
                '-rc', 'vbr',
                '-cq', '23',
                '-b:v', '0'
            ]
        elif codec == 'hevc' or codec == 'h265':
            # CPU HEVC
            encode_args = ['-c:v', 'libx265', '-preset', 'fast', '-crf', '23']
            if bitrate > 0:
                encode_args.extend(['-b:v', str(bitrate)])
        else:
            # CPU H.264
            encode_args = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '23']
        
        # Comando FFmpeg
        cmd = [
            'ffmpeg', '-y',
            '-i', str(current_input),
            '-loop', '1', '-i', str(clip['lower_third_png']),
            '-filter_complex', filter_complex,
            *encode_args,
            '-c:a', 'copy',
            '-shortest',
            '-movflags', '+faststart',
            str(current_output)
        ]
        
        # Executa
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            
            if result.returncode != 0:
                print(f"    ❌ Erro FFmpeg: {result.stderr[:300]}")
                # Limpa arquivos temporários
                for temp_file in temp_outputs:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                return False
            
            print(f"    ✅ Lower third {idx+1} aplicado!")
            
            # Atualiza input para próxima iteração
            if idx < len(clips_with_lt) - 1:
                current_input = current_output
            
        except subprocess.TimeoutExpired:
            print(f"    ❌ Timeout no overlay {idx+1}")
            # Limpa arquivos temporários
            for temp_file in temp_outputs:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            return False
        except Exception as e:
            print(f"    ❌ Erro: {e}")
            # Limpa arquivos temporários
            for temp_file in temp_outputs:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            return False
    
    # Limpa arquivos temporários
    for temp_file in temp_outputs:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                print(f"    🧹 Removido temporário: {os.path.basename(temp_file)}")
            except:
                pass
    
    print("\n    ✅ Todos os lower thirds aplicados com sucesso!")
    return True

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def main():
    start_time = time.time()
    
    print("🎨 Etapa 2B - Aplicação de Lower Thirds no Teaser")
    print("=" * 70)
    print("🎯 Objetivo: Aplicar lower thirds nos clipes do teaser")
    print("⚡ Re-encodando com HEVC para compatibilidade")
    print("=" * 70)
    print()
    
    # 1. Encontra arquivos necessários
    print("📁 Procurando arquivos necessários...")
    
    teaser_path = find_latest_file("*_teaser_sequential.mp4")
    transcript_path = find_latest_file("*_concatenated_videos_transcript.json")
    gpt_debug_path = find_latest_file("*_gpt_request_debug.json")
    locations_path = find_latest_file("*_video_locations.json")
    
    if not teaser_path:
        print("❌ Teaser não encontrado! Execute a etapa 2 primeiro.")
        return
    
    if not transcript_path:
        print("❌ Transcript não encontrado! Execute a etapa 2 primeiro.")
        return
    
    if not gpt_debug_path:
        print("❌ GPT debug não encontrado! Execute a etapa 2 primeiro.")
        return
    
    if not locations_path:
        print("❌ Locations não encontrado! Execute a etapa 1b primeiro.")
        return
    
    print(f"    ✅ Teaser: {os.path.basename(teaser_path)}")
    print(f"    ✅ Transcript: {os.path.basename(transcript_path)}")
    print(f"    ✅ GPT Debug: {os.path.basename(gpt_debug_path)}")
    print(f"    ✅ Locations: {os.path.basename(locations_path)}")
    
    # 2. Carrega dados
    print("\n📖 Carregando dados...")
    
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        print(f"    ✅ Transcript: {len(transcript_data.get('segments', []))} segmentos")
    except Exception as e:
        print(f"    ❌ Erro ao carregar transcript: {e}")
        return
    
    try:
        with open(gpt_debug_path, 'r', encoding='utf-8') as f:
            gpt_debug = json.load(f)
        
        # Extrai resposta do GPT
        gpt_response = None
        if 'response_content' in gpt_debug:
            gpt_response = gpt_debug['response_content']
        elif 'request_data' in gpt_debug:
            # Tenta extrair de outro formato (versões antigas)
            pass
        
        if not gpt_response:
            print("    ⚠️ Resposta do GPT não encontrada no debug (arquivo antigo)")
            print("\n" + "=" * 70)
            print("💡 SOLUÇÃO:")
            print("   Execute a etapa 2 novamente para gerar um novo arquivo de debug")
            print("   com a resposta do GPT salva:")
            print()
            print("   python etapa2.py")
            print()
            print("   Depois execute esta etapa novamente:")
            print("   python etapa2b.py")
            print("=" * 70)
            return
        
        print(f"    ✅ GPT Response: {gpt_response[:50]}...")
    except Exception as e:
        print(f"    ❌ Erro ao carregar GPT debug: {e}")
        return
    
    try:
        with open(locations_path, 'r', encoding='utf-8') as f:
            locations_data = json.load(f)
        print(f"    ✅ Locations: {len(locations_data)} vídeos com GPS")
    except Exception as e:
        print(f"    ❌ Erro ao carregar locations: {e}")
        return
    
    # 3. Constrói timeline dos vídeos originais
    print("\n🗺️  Construindo timeline dos vídeos originais...")
    timeline = build_video_timeline(SOURCES_DIR)
    
    if not timeline:
        print("    ❌ Não foi possível construir timeline")
        return
    
    print(f"    ✅ Timeline: {len(timeline)} vídeos")
    print(f"    ⏱️  Duração total: {format_time(timeline[-1]['end_time'])}")
    
    # 4. Mapeia clipes do teaser para vídeos originais
    print("\n🔗 Mapeando clipes do teaser...")
    clips_mapping = map_teaser_clips_to_videos(
        transcript_data,
        gpt_response,
        timeline,
        locations_data
    )
    
    if not clips_mapping:
        print("    ❌ Não foi possível mapear clipes")
        return
    
    print(f"    ✅ Clipes mapeados: {len(clips_mapping)}")
    print(f"    📍 Com lower third: {sum(1 for c in clips_mapping if c['has_lower_third'])}")
    print(f"    ❌ Sem lower third: {sum(1 for c in clips_mapping if not c['has_lower_third'])}")
    
    # DEBUG: Mostra todos os clipes mapeados
    print("\n📋 DEBUG - Todos os clipes mapeados:")
    for idx, clip in enumerate(clips_mapping, 1):
        status = "✅" if clip['has_lower_third'] else "❌"
        print(f"    {status} Clipe {idx}: {clip['video_name']}")
        print(f"        Timestamp no concat: {clip['start_in_concat']:.1f}s")
        print(f"        Timestamp no teaser: {clip['start_in_teaser']:.1f}s-{clip['end_in_teaser']:.1f}s")
        if clip['has_lower_third']:
            print(f"        Lower third: {os.path.basename(clip['lower_third_png'])}")
    
    # Mostra vídeos com GPS disponíveis
    print("\n📍 DEBUG - Vídeos com GPS disponíveis:")
    for video_name in sorted(locations_data.keys())[:10]:  # Mostra os primeiros 10
        print(f"    • {video_name}")
    if len(locations_data) > 10:
        print(f"    ... e mais {len(locations_data) - 10} vídeos")
    
    # Mostra detalhes dos clipes com lower third
    print("\n📋 Clipes com lower third:")
    for clip in clips_mapping:
        if clip['has_lower_third']:
            print(f"    • {clip['video_name']} @ {clip['start_in_teaser']:.1f}s-{clip['end_in_teaser']:.1f}s")
    
    # 5. Aplica lower thirds
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"{timestamp}_teaser_with_lower_thirds.mp4")
    
    success = apply_lower_thirds_to_teaser(
        teaser_path,
        clips_mapping,
        output_path
    )
    
    if not success:
        print("\n❌ Falha ao aplicar lower thirds")
        return
    
    # 6. Verifica resultado
    if not os.path.exists(output_path):
        print("\n❌ Arquivo de saída não foi criado")
        return
    
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    duration = get_video_duration(output_path)
    
    # Verifica se usou NVENC
    has_nvenc = check_nvenc_support()
    gpu_status = "🎮 NVIDIA GPU (NVENC)" if has_nvenc else "💻 CPU"
    
    # Resultado final
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("✅ Teaser com lower thirds gerado com sucesso!")
    print(f"📁 Arquivo: {output_path}")
    print(f"💾 Tamanho: {file_size:.2f} MB")
    print(f"⏱️  Duração: {format_time(duration) if duration else 'N/A'}")
    print(f"🕐 Tempo de processamento: {format_time(total_time)}")
    print(f"⚙️  Aceleração: {gpu_status}")
    print()
    if has_nvenc:
        minutes_saved = max(0, (total_time * 2) - total_time) / 60
        print(f"⚡ Economia estimada com NVENC: ~{minutes_saved:.1f} minutos!")
        print()
    print("🎯 Próximo passo: Execute etapa 3 para adicionar BGM")
    print("   (use o teaser com lower thirds em vez do teaser original)")
    print("=" * 70)

if __name__ == "__main__":
    main()

