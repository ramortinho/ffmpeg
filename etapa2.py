#!/usr/bin/env python3
"""
Programa para gerar teaser do vídeo concatenado da etapa 1
Etapa 2: Transcrição via OpenAI API + análise + geração de teaser sequencial
"""

import os
import subprocess
import json
import tempfile
import requests
from pathlib import Path
from datetime import datetime, timedelta
import time
import re

# Importar apenas a API key do arquivo externo
from config import OPENAI_API_KEY

# =============================================================================
# CONFIGURAÇÕES - ALTERE AQUI CONFORME NECESSÁRIO
# =============================================================================

# Diretórios
INPUT_DIR = "output"
OUTPUT_DIR = "output"

# Configurações da API OpenAI
OPENAI_WHISPER_MODEL = "whisper-1"  # Modelo da API OpenAI
OPENAI_GPT_MODEL = "gpt-4o-mini"  # Modelo para análise de conteúdo
LANGUAGE = "pt"  # pt, en, es, etc.

# Configurações do teaser
TEASER_DURATION = 60  # Duração total do teaser em segundos
TARGET_TEASER_DURATION = 60.0  # Duração desejada do teaser (segundos)
MIN_CLIP_DURATION = 5.0        # Duração mínima de cada clipe (segundos)
MAX_CLIP_DURATION = 6.0        # Duração máxima de cada clipe (segundos)
MIN_GAP_BETWEEN_CLIPS = 5.0    # Gap mínimo entre clipes (segundos)
CLIP_OFFSET = 1.0     # Offset de 1 segundo entre clipes para evitar travamentos

# Configurações de debug
CLEANUP_TEMP_FILES = True  # Manter arquivos temporários para análise
SKIP_TRANSCRIPTION_IF_EXISTS = True  # Pular transcrição se já existir arquivo temporário
CHUNK_DURATION_MINUTES = 10  # Duração de cada chunk em minutos para evitar timeout

# Configurações de análise de texto - DINÂMICAS
# As keywords serão geradas dinamicamente pelo GPT-4o-mini baseadas no conteúdo

# Configurações de vídeo - ULTRA OTIMIZADO PARA 4K
OUTPUT_WIDTH = None  # Manter largura original (4K)
OUTPUT_HEIGHT = None  # Manter altura original (4K)
VIDEO_CODEC = 'libx264'  # Re-encodificar para evitar travamentos
VIDEO_PRESET = 'ultrafast'  # Preset mais rápido
VIDEO_QUALITY = '18'  # Qualidade alta
AUDIO_CODEC = 'aac'
AUDIO_BITRATE = '128k'

# =============================================================================

def validate_config():
    """Valida as configurações do programa"""
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Diretório de entrada '{INPUT_DIR}' não encontrado!")
        return False
    
    if TEASER_DURATION <= 0:
        print("❌ TEASER_DURATION deve ser maior que 0!")
        return False
    
    if TARGET_TEASER_DURATION <= 0:
        print("❌ TARGET_TEASER_DURATION deve ser maior que 0!")
        return False
    
    if MIN_CLIP_DURATION <= 0 or MAX_CLIP_DURATION <= 0:
        print("❌ Durações de clipe devem ser maiores que 0!")
        return False
    
    if MIN_CLIP_DURATION > MAX_CLIP_DURATION:
        print("❌ MIN_CLIP_DURATION não pode ser maior que MAX_CLIP_DURATION!")
        return False
    
    if OPENAI_API_KEY == "sua_api_key_aqui":
        print("❌ Configure sua OPENAI_API_KEY no arquivo!")
        return False
    
    return True

def find_latest_video():
    """Encontra o vídeo mais recente na pasta output"""
    # Buscar especificamente por arquivos concatenated_videos.mp4
    video_files = []
    for pattern in ['*concatenated_videos.mp4', '*concatenated_videos.MP4']:
        video_files.extend(Path(INPUT_DIR).glob(pattern))
    
    if not video_files:
        print(f"❌ Nenhum vídeo concatenado encontrado na pasta '{INPUT_DIR}'")
        # Fallback para qualquer vídeo mp4
        for ext in ['*.mp4', '*.MP4']:
            video_files.extend(Path(INPUT_DIR).glob(ext))
        
        if not video_files:
            print(f"❌ Nenhum vídeo encontrado na pasta '{INPUT_DIR}'")
            return None
    
    # Ordenar por data de modificação (mais recente primeiro)
    latest_video = max(video_files, key=lambda x: x.stat().st_mtime)
    print(f"    📁 Arquivo selecionado: {latest_video.name}")
    return str(latest_video)

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

def get_transcript_cache_path(video_path):
    """Gera caminho do cache de transcrição baseado no vídeo"""
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(OUTPUT_DIR, f"{video_name}_transcript.json")

def load_cached_transcript(cache_path):
    """Carrega transcrição do cache se existir"""
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"      ⚠️ Erro ao carregar cache: {e}")
    return None

def save_transcript_cache(transcript_data, cache_path):
    """Salva transcrição no cache"""
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(transcript_data, f, ensure_ascii=False, indent=2)
        print(f"      💾 Transcrição salva em cache: {os.path.basename(cache_path)}")
    except Exception as e:
        print(f"      ⚠️ Erro ao salvar cache: {e}")

def split_video_into_chunks(video_path, chunk_duration_minutes):
    """Divide vídeo em chunks para evitar timeout da API"""
    print(f"    ✂️ Dividindo vídeo em chunks de {chunk_duration_minutes} minutos...")
    
    video_duration = get_video_duration(video_path)
    if not video_duration:
        return []
    
    chunk_duration_seconds = chunk_duration_minutes * 60
    chunks = []
    
    for i, start_time in enumerate(range(0, int(video_duration), chunk_duration_seconds)):
        end_time = min(start_time + chunk_duration_seconds, video_duration)
        
        chunk_path = os.path.join(OUTPUT_DIR, f"chunk_{i+1:02d}_{start_time:.0f}s-{end_time:.0f}s.mp4")
        
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_time),
            '-i', video_path,
            '-t', str(end_time - start_time),
            '-c', 'copy',
            chunk_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            chunks.append({
                'path': chunk_path,
                'start': start_time,
                'end': end_time,
                'index': i + 1
            })
            print(f"      ✅ Chunk {i+1}: {start_time:.0f}s - {end_time:.0f}s")
        else:
            print(f"      ❌ Erro no chunk {i+1}: {result.stderr}")
    
    return chunks

def extract_audio_for_api(video_path):
    """Extrai áudio otimizado para API OpenAI"""
    print("    🔊 Extraindo áudio para API OpenAI...")
    
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_audio:
        audio_path = temp_audio.name
    
    # Extrair áudio otimizado para API
    cmd_extract = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vn',  # Sem vídeo
        '-acodec', 'mp3',  # Codec MP3 para API
        '-ar', '16000',  # Sample rate 16kHz
        '-ac', '1',  # Mono
        '-b:a', '64k',  # Bitrate baixo para API
        audio_path
    ]
    
    result = subprocess.run(cmd_extract, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"      ❌ Erro ao extrair áudio: {result.stderr}")
        return None
    
    return audio_path

def transcribe_with_openai_api(audio_path):
    """Transcreve áudio usando API OpenAI Whisper"""
    print("    🤖 Transcrevendo com OpenAI Whisper API...")
    
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    with open(audio_path, 'rb') as audio_file:
        files = {
            'file': (audio_path, audio_file, 'audio/mpeg'),
            'model': (None, OPENAI_WHISPER_MODEL),
            'language': (None, LANGUAGE),
            'response_format': (None, 'verbose_json'),
            'timestamp_granularities': (None, 'segment')
        }
        
        try:
            response = requests.post(url, headers=headers, files=files, timeout=300)
            response.raise_for_status()
            
            transcript_data = response.json()
            print(f"      ✅ Transcrição concluída via API")
            return transcript_data
            
        except requests.exceptions.RequestException as e:
            print(f"      ❌ Erro na API: {e}")
            return None

def generate_teaser_segments(segments):
    """Gera segmentos para teaser narrativo usando GPT-4o-mini - OTIMIZADO COM IDs"""
    print("    🧠 Analisando conteúdo e criando teaser narrativo...")
    
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # OTIMIZAÇÃO: Criar JSON simplificado com apenas dados essenciais
    simplified_segments = []
    for i, seg in enumerate(segments):
        simplified_segments.append({
            "id": i,
            "start": seg['start'],
            "end": seg['end'],
            "text": seg['text'].strip()
        })
    
    # Usar todos os segmentos disponíveis
    total_segments = len(simplified_segments)
    
    # Criar contexto com TODOS os segmentos (sem limitação)
    segments_context = ""
    for i, seg in enumerate(simplified_segments):
        segments_context += f"ID {seg['id']}: {seg['start']:.1f}s-{seg['end']:.1f}s - {seg['text'][:80]}...\n"
    
    print(f"      📝 Enviando TODOS os {len(simplified_segments)} segmentos para GPT")
    
    prompt = f"""
Analise estes segmentos de vídeo e selecione os mais importantes para criar um teaser narrativo de aproximadamente {TARGET_TEASER_DURATION:.0f} segundos.

TODOS OS SEGMENTOS DISPONÍVEIS (ID: start-end - texto):
{segments_context}

INSTRUÇÕES:
1. Selecione segmentos que formem uma narrativa interessante
2. DISTRIBUA por TODO o vídeo (início, meio e fim)
3. Priorize momentos de emoção, surpresa, admiração, ação
4. Cada segmento deve ter entre {MIN_CLIP_DURATION:.0f} e {MAX_CLIP_DURATION:.0f} segundos
5. Mantenha ordem cronológica (do início para o fim do vídeo)

IMPORTANTE: Selecione segmentos de diferentes partes do vídeo, não apenas do início!

Responda APENAS com os IDs dos segmentos separados por vírgula, em ordem sequencial.
Exemplo: 0,15,32,48,65,82,99,116,133,150
"""
    
    data = {
        "model": OPENAI_GPT_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 200,
        "temperature": 0.1
    }
    
    # Salvar JSON enviado para debug
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file = os.path.join(OUTPUT_DIR, f"{timestamp}_gpt_request_debug.json")
    try:
        with open(debug_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": timestamp,
                "total_segments": len(simplified_segments),
                "prompt": prompt,
                "request_data": data
            }, f, ensure_ascii=False, indent=2)
        print(f"      💾 Debug JSON salvo: {os.path.basename(debug_file)}")
    except Exception as e:
        print(f"      ⚠️ Erro ao salvar debug JSON: {e}")
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        selected_indices = result['choices'][0]['message']['content'].strip()
        
        # Processar resposta do GPT - mapear IDs de volta para segments
        selected_ids = [int(id_str.strip()) for id_str in selected_indices.split(',') if id_str.strip().isdigit()]
        print(f"      🔍 DEBUG: IDs selecionados pelo GPT: {len(selected_ids)}")
        
        # Verificar se selecionou quantidade adequada
        if len(selected_ids) < 8:
            print(f"      ⚠️ GPT selecionou apenas {len(selected_ids)} segmentos, completando...")
            
            # Adicionar segmentos do meio e fim se necessário
            all_valid_ids = set(selected_ids)
            remaining_needed = 12 - len(selected_ids)  # Completar até 12 segmentos
            
            # Buscar segmentos do meio (30-70% do vídeo)
            meio_start_idx = len(segments) // 3
            meio_end_idx = 2 * len(segments) // 3
            meio_candidates = [i for i in range(meio_start_idx, meio_end_idx) if i not in all_valid_ids]
            
            # Buscar segmentos do fim (últimos 30%)
            fim_start_idx = int(len(segments) * 0.7)
            fim_candidates = [i for i in range(fim_start_idx, len(segments)) if i not in all_valid_ids]
            
            # Adicionar candidatos alternativos
            additional_candidates = meio_candidates[:remaining_needed//2] + fim_candidates[:remaining_needed//2]
            if len(additional_candidates) < remaining_needed:
                # Se ainda não tem o suficiente, pegar qualquer segmento válido
                all_candidates = [i for i in range(len(segments)) if i not in all_valid_ids]
                additional_candidates.extend(all_candidates[:remaining_needed - len(additional_candidates)])
            
            selected_ids.extend(additional_candidates[:remaining_needed])
            print(f"      ✅ Completado com {len(additional_candidates[:remaining_needed])} segmentos adicionais")
        
        # Mapear IDs de volta para segments (mapeamento direto e preciso)
        selected_segments = []
        for selected_id in selected_ids:
            if 0 <= selected_id < len(segments):
                selected_segments.append(segments[selected_id])
                print(f"      ✅ Mapeado ID {selected_id}: {segments[selected_id]['start']:.1f}s-{segments[selected_id]['end']:.1f}s - {segments[selected_id]['text'][:50]}...")
            else:
                print(f"      ⚠️ ID inválido: {selected_id}")
        
        # Verificar distribuição temporal
        if selected_segments:
            timestamps = [seg['start'] for seg in selected_segments]
            max_timestamp = max(timestamps)
            video_duration = max([seg['end'] for seg in segments])
            
            print(f"      🔍 DEBUG: Timestamp máximo: {max_timestamp:.1f}s de {video_duration:.1f}s total")
            
            # Se ainda está concentrado no início, forçar distribuição
            if max_timestamp < (video_duration * 0.3):
                print(f"      ⚠️ Ainda concentrado no início - forçando distribuição...")
                
                # Manter alguns do início e adicionar do meio/fim
                inicio_segments = [seg for seg in selected_segments if seg['start'] < video_duration * 0.2]
                selected_segments = inicio_segments[:2]  # Manter apenas 2 do início
                
                # Adicionar do meio
                meio_segments = [seg for seg in segments if video_duration * 0.3 < seg['start'] < video_duration * 0.7]
                if meio_segments:
                    selected_segments.extend(meio_segments[::len(meio_segments)//3])  # 3 do meio
                
                # Adicionar do fim
                fim_segments = [seg for seg in segments if seg['start'] > video_duration * 0.8]
                if fim_segments:
                    selected_segments.extend(fim_segments[::len(fim_segments)//2])  # 2 do fim
                
                # Remover duplicatas e ordenar
                selected_segments = list({seg['start']: seg for seg in selected_segments}.values())
                selected_segments.sort(key=lambda x: x['start'])
                
                print(f"      ✅ Distribuição forçada: {len(selected_segments)} segmentos")
                if selected_segments:
                    timestamps = [seg['start'] for seg in selected_segments]
                    print(f"      📊 Timestamps: {min(timestamps):.1f}s - {max(timestamps):.1f}s")
        
        # Aplicar filtro anti-sobreposição baseado na duração desejada
        filtered_segments = []
        min_gap = MIN_GAP_BETWEEN_CLIPS
        max_segments = int(TARGET_TEASER_DURATION / MIN_CLIP_DURATION)  # Máximo baseado na duração desejada
        
        for segment in selected_segments:
            if not filtered_segments:
                filtered_segments.append(segment)
            else:
                # Verificar se há sobreposição ou gap muito pequeno
                has_overlap = False
                for selected in filtered_segments:
                    if (segment['start'] < selected['end'] and segment['end'] > selected['start']):
                        has_overlap = True
                        break
                    gap = min(abs(segment['start'] - selected['end']), abs(selected['start'] - segment['end']))
                    if gap < min_gap:
                        has_overlap = True
                        break
                
                if not has_overlap:
                    filtered_segments.append(segment)
                    if len(filtered_segments) >= max_segments:
                        break
        
        # Ordenar por timestamp para manter ordem sequencial
        filtered_segments.sort(key=lambda x: x['start'])
        
        print(f"      ✅ {len(filtered_segments)} segmentos selecionados para teaser narrativo")
        print(f"      📝 Duração total: {sum(seg['end'] - seg['start'] for seg in filtered_segments):.1f}s")
        print(f"      🎯 Meta: ~{TARGET_TEASER_DURATION:.0f}s de teaser")
        
        # Verificar se atingiu a meta
        total_duration = sum(seg['end'] - seg['start'] for seg in filtered_segments)
        if total_duration >= TARGET_TEASER_DURATION * 0.8:  # 80% da meta
            print(f"      ✅ Meta atingida! ({total_duration:.1f}s)")
        else:
            print(f"      ⚠️ Meta não atingida ({total_duration:.1f}s) - teaser mais curto")
        
        return filtered_segments
        
    except requests.exceptions.RequestException as e:
        print(f"      ❌ Erro na API GPT: {e}")
        # Fallback: retornar primeiros 8 segmentos
        return segments[:8]

def transcribe_video_api(video_path):
    """Transcreve o vídeo usando API OpenAI com chunks e cache - ULTRA RÁPIDO"""
    print("🎤 Passo 1/4: TRANSCREVENDO vídeo com OpenAI API...")
    transcribe_start = time.time()
    
    # Verificar cache primeiro
    cache_path = get_transcript_cache_path(video_path)
    if SKIP_TRANSCRIPTION_IF_EXISTS:
        cached_data = load_cached_transcript(cache_path)
        if cached_data:
            print(f"    💾 Usando transcrição em cache: {os.path.basename(cache_path)}")
            transcribe_time = time.time() - transcribe_start
            print(f"✅ TRANSCRIÇÃO (cache) concluída em {format_time(transcribe_time)}")
            print(f"    📊 Total de segmentos: {len(cached_data.get('segments', []))}")
            return cached_data
    
    # Obter duração do vídeo
    video_duration = get_video_duration(video_path)
    if not video_duration:
        print("    ❌ Erro ao obter duração do vídeo")
        return None
    
    print(f"    📹 Duração do vídeo: {format_time(video_duration)}")
    
    # Decidir se usar chunks baseado na duração
    use_chunks = video_duration > (CHUNK_DURATION_MINUTES * 60)
    
    if use_chunks:
        print(f"    🔄 Vídeo longo detectado - usando chunks de {CHUNK_DURATION_MINUTES} minutos")
        
        # Dividir em chunks
        chunks = split_video_into_chunks(video_path, CHUNK_DURATION_MINUTES)
        if not chunks:
            print("    ❌ Erro ao dividir vídeo em chunks")
            return None
        
        # Transcrever cada chunk
        all_segments = []
        full_text = ""
        
        for chunk in chunks:
            print(f"    🎯 Processando chunk {chunk['index']}/{len(chunks)}...")
            
            # Extrair áudio do chunk
            audio_path = extract_audio_for_api(chunk['path'])
            if not audio_path:
                continue
            
            # Transcrever chunk
            chunk_data = transcribe_with_openai_api(audio_path)
            
            # Cleanup áudio temporário
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            if chunk_data and 'segments' in chunk_data:
                # Ajustar timestamps dos segmentos para o vídeo original
                for segment in chunk_data['segments']:
                    segment['start'] += chunk['start']
                    segment['end'] += chunk['start']
                    all_segments.append(segment)
                
                full_text += chunk_data.get('text', '') + " "
            
            # Cleanup chunk temporário
            if os.path.exists(chunk['path']):
                os.remove(chunk['path'])
        
        # Combinar resultados
        transcript_data = {
            'text': full_text.strip(),
            'segments': all_segments,
            'language': LANGUAGE
        }
        
    else:
        # Processar vídeo completo (método original)
        print("    🎯 Processando vídeo completo...")
        
        # Extrair áudio para API
        audio_path = extract_audio_for_api(video_path)
        if not audio_path:
            return None
        
        # Transcrever com API OpenAI
        transcript_data = transcribe_with_openai_api(audio_path)
        
        # Cleanup
        if os.path.exists(audio_path):
            os.remove(audio_path)
    
    if not transcript_data:
        return None
    
    # Salvar no cache
    save_transcript_cache(transcript_data, cache_path)
    
    transcribe_time = time.time() - transcribe_start
    print(f"✅ TRANSCRIÇÃO concluída em {format_time(transcribe_time)}")
    print(f"    📊 Total de segmentos: {len(transcript_data.get('segments', []))}")
    
    return transcript_data

def analyze_segments_sequential(transcript_data):
    """Cria teaser narrativo usando GPT-4o-mini"""
    print("🔍 Passo 2/4: CRIANDO teaser narrativo com GPT-4o-mini...")
    analyze_start = time.time()
    
    segments = transcript_data.get('segments', [])
    if not segments:
        print("    ❌ Nenhum segmento encontrado na transcrição!")
        return []
    
    full_text = transcript_data.get('text', '')
    
    # Usar GPT-4o-mini para selecionar segmentos para teaser narrativo
    selected_segments = generate_teaser_segments(segments)
    
    analyze_time = time.time() - analyze_start
    print(f"✅ ANÁLISE concluída em {format_time(analyze_time)}")
    print(f"    📊 Total de segmentos disponíveis: {len(segments)}")
    print(f"    📊 Segmentos selecionados para teaser: {len(selected_segments)}")
    
    if selected_segments:
        print("    🎯 Segmentos selecionados para teaser narrativo:")
        for i, seg in enumerate(selected_segments, 1):
            print(f"      {i}. {seg['start']:.1f}s - {seg['end']:.1f}s ({seg['end'] - seg['start']:.1f}s)")
            print(f"         Texto: {seg['text'][:50]}...")
    
    return selected_segments

def find_nearest_keyframes(video_path, start_time, end_time):
    """Encontra os keyframes mais próximos para evitar frames congelados"""
    try:
        # Buscar keyframes próximos ao timestamp de início
        keyframe_cmd = [
            'ffprobe', '-v', 'quiet', '-select_streams', 'v:0',
            '-show_entries', 'frame=pkt_pts_time', '-of', 'csv=p=0',
            '-read_intervals', f'{max(0, start_time-2)}%{start_time+2}',
            video_path
        ]
        result = subprocess.run(keyframe_cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            keyframes = [float(kf) for kf in result.stdout.strip().split('\n') if kf]
            if keyframes:
                # Encontrar keyframe mais próximo ao start_time
                nearest_start = min(keyframes, key=lambda x: abs(x - start_time))
                # Ajustar end_time para manter a duração original
                duration = end_time - start_time
                adjusted_end = nearest_start + duration
                
                print(f"        🔑 Keyframe encontrado: {start_time:.1f}s -> {nearest_start:.1f}s")
                return nearest_start, adjusted_end
        
        # Se não encontrar keyframes, usar timestamps originais
        return start_time, end_time
        
    except Exception as e:
        print(f"        ⚠️ Erro ao buscar keyframes: {e}")
        return start_time, end_time

def extract_clips_with_offset(video_path, segments):
    """Extrai clipes com offset para evitar travamentos"""
    print("✂️  Passo 3/4: EXTRAINDO clipes exatamente onde o Whisper identificou as falas...")
    extract_start = time.time()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    clip_files = []
    
    for i, segment in enumerate(segments, 1):
        start_time = segment['start']
        end_time = segment['end']
        duration = end_time - start_time
        
        # Ajustar clipes para 5-6 segundos para melhor narrativa
        if duration < MIN_CLIP_DURATION:
            # Estender para duração mínima, centralizando o conteúdo original
            extension = (MIN_CLIP_DURATION - duration) / 2
            start_time = max(0, start_time - extension)
            end_time = start_time + MIN_CLIP_DURATION
            duration = MIN_CLIP_DURATION
        elif duration > MAX_CLIP_DURATION:
            # Reduzir para duração máxima, mantendo o início
            end_time = start_time + MAX_CLIP_DURATION
            duration = MAX_CLIP_DURATION
        
        # Nome do clipe com timestamp no formato do teaser
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clip_file = os.path.join(OUTPUT_DIR, f"{timestamp}_clip_{i:02d}_{start_time:.1f}s-{end_time:.1f}s.mp4")
        
        # Cortar exatamente onde o Whisper indicou - SIMPLES E DIRETO
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_time),  # Início exato da fala
            '-i', video_path,  # Input DEPOIS do -ss para precisão
            '-t', str(end_time - start_time),  # Duração exata da fala
            '-c', 'copy',  # Copy codec - SEM RE-ENCODIFICAÇÃO
            '-avoid_negative_ts', 'make_zero',  # Evitar problemas de timestamp
            clip_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # Verificar se o arquivo foi criado e tem tamanho
            if os.path.exists(clip_file) and os.path.getsize(clip_file) > 0:
                clip_files.append(clip_file)
                file_size = os.path.getsize(clip_file) / (1024 * 1024)
                duration = end_time - start_time
                print(f"    ✅ Clipe {i}: {start_time:.1f}s - {end_time:.1f}s ({duration:.1f}s) - {file_size:.1f}MB")
            else:
                print(f"    ❌ Clipe {i}: Arquivo vazio ou não criado - {clip_file}")
        else:
            print(f"    ❌ Erro no clipe {i}: {result.stderr}")
            print(f"    🔧 Comando: {' '.join(cmd)}")
    
    extract_time = time.time() - extract_start
    print(f"✅ EXTRAÇÃO concluída em {format_time(extract_time)}")
    print(f"    📁 {len(clip_files)} clipes extraídos com sucesso")
    
    return clip_files

def check_clip_properties(clip_files):
    """Verifica propriedades dos clipes para debug"""
    print("    🔍 Verificando propriedades dos clipes...")
    
    for i, clip_file in enumerate(clip_files, 1):
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format', '-show_streams',
            clip_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
                audio_stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), None)
                
                if video_stream and audio_stream:
                    print(f"      Clipe {i}: {video_stream['codec_name']} {video_stream['width']}x{video_stream['height']} @{video_stream.get('r_frame_rate', 'N/A')} | {audio_stream['codec_name']} @{audio_stream.get('sample_rate', 'N/A')}")
                else:
                    print(f"      Clipe {i}: Propriedades não encontradas")
            except:
                print(f"      Clipe {i}: Erro ao analisar propriedades")
        else:
            print(f"      Clipe {i}: Erro ao obter propriedades")

def merge_clips_sequential(clip_files, output_path):
    """Mescla clipes usando Concat Demuxer com List File (mais robusto para copy codec)"""
    print("🎬 Passo 4/4: MESCLANDO clipes com Concat Demuxer + List File...")
    merge_start = time.time()
    
    if not clip_files:
        print("    ❌ Nenhum clipe para mesclar!")
        return False
    
    # Verificar propriedades dos clipes
    check_clip_properties(clip_files)
    
    if len(clip_files) == 1:
        # Para 1 clipe, apenas copia
        cmd = [
            'ffmpeg', '-y', 
            '-i', clip_files[0],
            '-c', 'copy',  # Copy codec sempre
            output_path
        ]
    else:
        # Para múltiplos clipes, usar concat demuxer com list file
        list_file = output_path.replace('.mp4', '_list.txt')
        
        # Criar arquivo de lista com caminhos absolutos
        with open(list_file, 'w') as f:
            for clip_file in clip_files:
                abs_path = os.path.abspath(clip_file)
                f.write(f"file '{abs_path}'\n")
        
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',  # Copy codec sempre
            '-avoid_negative_ts', 'make_zero',
            output_path
        ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Cleanup do arquivo de lista
    if len(clip_files) > 1:
        list_file = output_path.replace('.mp4', '_list.txt')
        if os.path.exists(list_file):
            os.remove(list_file)
    
    if result.returncode != 0:
        print(f"    ❌ Erro na mesclagem: {result.stderr}")
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
    
    print("🎬 ETAPA 2: Geração de Teaser - OPENAI API + CHUNKS + CACHE")
    print("⏱️  Resolução: ORIGINAL (4K) - SEM REDIMENSIONAMENTO")
    print("🔧 Codec: COPY (ultra rápido) | Áudio: COPY | API: OpenAI Whisper + GPT-4o-mini")
    print("🚀 ULTRA OTIMIZADO: API OpenAI + chunks + cache + keywords dinâmicas + copy codec + clipes 4s+ + sem repetições + timestamps precisos!")
    print(f"🔍 DEBUG: Limpeza de temporários = {'ATIVADA' if CLEANUP_TEMP_FILES else 'DESATIVADA'}")
    print(f"🔍 DEBUG: Pular transcrição se existir = {'ATIVADO' if SKIP_TRANSCRIPTION_IF_EXISTS else 'DESATIVADO'}")
    print(f"🔍 DEBUG: Chunks de {CHUNK_DURATION_MINUTES} minutos para vídeos longos")
    print("📁 Clipes temporários salvos em: output/")
    print("=" * 60)
    
    # Encontrar vídeo mais recente
    video_path = find_latest_video()
    if not video_path:
        return
    
    print(f"📹 Vídeo encontrado: {os.path.basename(video_path)}")
    
    # Transcrever vídeo com API OpenAI
    transcript_data = transcribe_video_api(video_path)
    if not transcript_data:
        print("❌ Falha na transcrição")
        return
    
    # Criar teaser narrativo com GPT-4o-mini
    segments = analyze_segments_sequential(transcript_data)
    
    if not segments:
        print("❌ Nenhum segmento adequado encontrado!")
        return
    
    # Mostrar segmentos selecionados
    print("\n📋 Segmentos selecionados (ordem sequencial):")
    for i, segment in enumerate(segments, 1):
        print(f"  {i}. {segment['start']:.1f}s - {segment['end']:.1f}s ({segment['end'] - segment['start']:.1f}s)")
        print(f"     Texto: {segment['text'][:100]}...")
        print()
    
    # Extrair clipes com offset
    clip_files = extract_clips_with_offset(video_path, segments)
    if not clip_files:
        print("❌ Nenhum clipe foi extraído com sucesso!")
        return
    
    # Mesclar clipes sequenciais
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    teaser_path = os.path.join(OUTPUT_DIR, f"{timestamp}_teaser_sequential.mp4")
    
    if not merge_clips_sequential(clip_files, teaser_path):
        print("❌ Erro ao mesclar clipes!")
        return
    
    # Resultado final
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("✅ TEASER SEQUENCIAL gerado com sucesso!")
    print(f"📁 Arquivo: {teaser_path}")
    print(f"⏱️  Tempo total: {format_time(total_time)}")
    
    if os.path.exists(teaser_path):
        file_size = os.path.getsize(teaser_path) / (1024 * 1024)
        print(f"📊 Tamanho: {file_size:.2f} MB")
    
    # Limpeza (controlada por parâmetro)
    if CLEANUP_TEMP_FILES:
        print("\n🧹 Limpando clipes temporários...")
        for clip_file in clip_files:
            if os.path.exists(clip_file):
                os.remove(clip_file)
        print("✅ Limpeza concluída!")
    else:
        print(f"\n🔍 DEBUG: Clipes temporários mantidos para análise:")
        for i, clip_file in enumerate(clip_files, 1):
            print(f"   {i}. {clip_file}")
        print("   💡 Altere CLEANUP_TEMP_FILES = True para limpar automaticamente")
    
    print("\n🚀 OTIMIZAÇÕES APLICADAS:")
    print("   • TRANSCRIÇÃO via OpenAI Whisper API (ultra rápida)")
    print("   • CHUNKS para vídeos longos (evita timeout da API)")
    print("   • CACHE de transcrição (evita reprocessamento)")
    print("   • KEYWORDS DINÂMICAS via GPT-4o-mini (baseadas no conteúdo)")
    print("   • ANÁLISE sequencial (mantém ordem do vídeo)")
    print("   • COPY CODEC (sem re-encodificação - ultra rápido)")
    print("   • CLIPES 4s+ (duração adequada)")
    print("   • FILTRO ANTI-REPETIÇÃO (gap mínimo 5s entre clipes)")
    print("   • CONCAT DEMUXER + LIST FILE (mesclagem robusta)")
    print("   • VERIFICAÇÃO DE PROPRIEDADES (debug de compatibilidade)")
    print("   • ORDEM sequencial preservada")
    print("   • DISTRIBUIÇÃO temporal (início, meio, fim do vídeo)")

if __name__ == "__main__":
    main()
