# 🎬 FFmpeg Video Processing Pipeline

Sistema automatizado para processamento de vídeos GoPro com geração de teaser inteligente usando IA.

## 🚀 Funcionalidades

- **Concatenação otimizada** de múltiplos vídeos GoPro
- **Normalização de áudio** com loudnorm
- **Transcrição automática** via OpenAI Whisper API
- **Geração de teaser narrativo** com GPT-4o-mini
- **Seleção automática de BGM** baseada na duração
- **Preservação de qualidade 4K** original
- **Codec HEVC mantido** (sem re-encodificação desnecessária)

## 📁 Estrutura do Projeto

```
ffmpeg/
├── etapa1.py          # Concatenação e normalização
├── etapa2.py          # Transcrição e geração de teaser
├── etapa3.py          # Adição de BGM
├── etapa4.py          # Criação do arquivo final
├── config.py          # Configurações da API OpenAI
├── sources/           # Vídeos originais (GoPro)
├── output/            # Arquivos processados
├── assets/            # Músicas de fundo (BGM)
└── venv/              # Ambiente virtual Python
```

## 🛠️ Instalação

### 1. Clonar o repositório
```bash
git clone https://github.com/ramortinho/ffmpeg.git
cd ffmpeg
```

**Nota**: O repositório usa a branch `main` como padrão.

### 2. Criar ambiente virtual
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. Instalar dependências
```bash
pip install requests openai-whisper
```

### 4. Instalar FFmpeg
- **Windows**: Baixar de https://ffmpeg.org/download.html
- **Linux**: `sudo apt install ffmpeg`
- **Mac**: `brew install ffmpeg`

### 5. Configurar API OpenAI
```bash
# Editar config.py
OPENAI_API_KEY = "sua_api_key_aqui"
```

## 🎯 Como Usar

### Pipeline Completo (Recomendado)
```bash
# 1. Colocar vídeos GoPro na pasta sources/
# 2. Executar pipeline completo
python etapa1.py && python etapa2.py && python etapa3.py && python etapa4.py
```

### Execução Individual
```bash
# Etapa 1: Concatenação e normalização
python etapa1.py

# Etapa 2: Transcrição e teaser
python etapa2.py

# Etapa 3: Adicionar BGM
python etapa3.py

# Etapa 4: Arquivo final
python etapa4.py
```

## 📋 Pré-requisitos

### Vídeos de Entrada
- **Formato**: MP4 (GoPro)
- **Resolução**: 4K (3840x2160)
- **Codec**: HEVC (H.265)
- **Localização**: Pasta `sources/`

### BGM (Background Music)
- **Formatos**: MP3, WAV, M4A, AAC, OGG
- **Localização**: Pasta `assets/`
- **Seleção**: Automática baseada na duração do teaser

## ⚙️ Configurações

### Etapa 1 - Concatenação
```python
MAX_VIDEOS = 59          # Máximo de vídeos a processar
TRIM_SECONDS = 2.0       # Segundos a remover do início/fim
AUDIO_FILTER = 'loudnorm' # Filtro de normalização
```

### Etapa 2 - Teaser
```python
TARGET_TEASER_DURATION = 60.0    # Duração desejada (segundos)
MIN_CLIP_DURATION = 5.0          # Duração mínima por clipe
MAX_CLIP_DURATION = 6.0          # Duração máxima por clipe
MIN_GAP_BETWEEN_CLIPS = 5.0      # Gap mínimo entre clipes
```

### Etapa 3 - BGM
```python
BGM_VOLUME_DB = -5       # Volume do BGM (dB)
AUDIO_CODEC = 'aac'      # Codec de áudio
AUDIO_BITRATE = '128k'   # Bitrate do áudio
```

## 🔧 Otimizações Implementadas

### Performance
- **Copy codec** para evitar re-encodificação
- **Chunking** para vídeos longos (>10min)
- **Cache de transcrição** para evitar reprocessamento
- **API OpenAI** para transcrição ultra-rápida

### Qualidade
- **Resolução 4K preservada** em todo o pipeline
- **Codec HEVC mantido** da GoPro original
- **Normalização inteligente** de áudio
- **Seleção narrativa** de segmentos com IA

### Usabilidade
- **Pipeline automatizado** de 4 etapas
- **Seleção automática** de BGM
- **Logs detalhados** com timing
- **Limpeza automática** de arquivos temporários

## 📊 Resultados Esperados

### Tempos de Processamento
- **Etapa 1**: ~30-60 segundos (concatenação)
- **Etapa 2**: ~2-5 minutos (transcrição + teaser)
- **Etapa 3**: ~3-10 segundos (BGM)
- **Etapa 4**: ~1-3 minutos (arquivo final)

### Arquivos Gerados
- `YYYYMMDD_HHMMSS_concatenated_videos.mp4` - Vídeo concatenado
- `YYYYMMDD_HHMMSS_teaser_sequential.mp4` - Teaser narrativo
- `YYYYMMDD_HHMMSS_teaser_with_bgm.mp4` - Teaser com BGM
- `YYYYMMDD_HHMMSS_FINAL_teaser_plus_full_video.mp4` - Arquivo final

## 🐛 Solução de Problemas

### Erro de API OpenAI
```
❌ Configure sua OPENAI_API_KEY no arquivo!
```
**Solução**: Editar `config.py` com sua chave da API OpenAI

### Erro de FFmpeg
```
❌ 'ffmpeg' não é reconhecido como comando
```
**Solução**: Instalar FFmpeg e adicionar ao PATH do sistema

### Vídeos não encontrados
```
❌ Nenhum vídeo encontrado na pasta 'sources'
```
**Solução**: Colocar vídeos MP4 na pasta `sources/`

### Problemas de codec
```
⚠️ Vídeos têm propriedades diferentes
```
**Solução**: Usar vídeos GoPro originais (HEVC) para melhor compatibilidade

## 📈 Melhorias Futuras

- [ ] Interface gráfica (GUI)
- [ ] Suporte a mais formatos de vídeo
- [ ] Configuração via arquivo JSON
- [ ] Processamento em lote
- [ ] Upload automático para YouTube
- [ ] Análise de sentimento dos segmentos
- [ ] Templates de teaser personalizáveis

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 👨‍💻 Autor

**Ramon Mortinho**
- GitHub: [@ramortinho](https://github.com/ramortinho)
- Projeto: [FFmpeg Video Processing Pipeline](https://github.com/ramortinho/ffmpeg)

## 🙏 Agradecimentos

- **OpenAI** pela API Whisper e GPT-4o-mini
- **FFmpeg** pela ferramenta de processamento de mídia
- **GoPro** pelos vídeos de alta qualidade
- **Python** pela linguagem de programação

---

⭐ **Se este projeto foi útil, considere dar uma estrela!** ⭐
