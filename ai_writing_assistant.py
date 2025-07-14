from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from groq import Groq
import json
import os
from datetime import datetime
import threading
import queue
import time

# Load environment variables from .env file
load_dotenv()
app = Flask(__name__)

# Check if .env file exists
if os.path.exists('.env'):
    print(".env file found")
    with open('.env', 'r') as f:
        print(f".env contents: {f.read()}")
else:
    print(".env file NOT found in current directory")
    print(f"Current directory: {os.getcwd()}")

api_key = os.getenv("GROQ_API_KEY")
#print(f"API Key loaded: {api_key[:10]}..." if api_key else "No API key found")
#client = Groq(api_key=os.getenv("GROQ_API_KEY"))
if not api_key:
    print("Please set your GROQ_API_KEY in the .env file")
    exit()

client = Groq(api_key=api_key)

# Available models
MODELS = {
    "llama-3.1-70b-versatile": "Llama 3.1 70B (Versatile)",
    "llama-3.1-8b-instant": "Llama 3.1 8B (Fast)",
    "gemma2-9b-it": "Gemma 2 9B",
    "mixtral-8x7b-32768": "Mixtral 8x7B",
    "llama-3.2-90b-text-preview": "Llama 3.2 90B (Preview)"
}

# Writing prompts and templates
WRITING_PROMPTS = {
    "creative": "Write a creative story about: ",
    "blog": "Write a blog post about: ",
    "email": "Write a professional email about: ",
    "essay": "Write an essay about: ",
    "summary": "Summarize the following text: ",
    "rewrite": "Rewrite the following text to be more engaging: ",
    "grammar": "Fix grammar and improve the following text: ",
    "translate": "Translate the following text: ",
    "outline": "Create an outline for: ",
    "ideas": "Brainstorm ideas about: "
}

# Tone options
TONES = {
    "professional": "Write in a professional tone",
    "casual": "Write in a casual, friendly tone",
    "formal": "Write in a formal, academic tone",
    "creative": "Write in a creative, imaginative tone",
    "persuasive": "Write in a persuasive, convincing tone",
    "informative": "Write in an informative, educational tone"
}

def create_system_prompt(writing_type, tone, length):
    """Create a system prompt based on user preferences"""
    base_prompt = f"You are an expert AI writing assistant. "
    
    if writing_type in WRITING_PROMPTS:
        base_prompt += f"You specialize in {writing_type} writing. "
    
    if tone in TONES:
        base_prompt += f"{TONES[tone]}. "
    
    length_guidance = {
        "short": "Keep your response concise and to the point (150-300 words).",
        "medium": "Provide a well-developed response (300-600 words).",
        "long": "Write a comprehensive, detailed response (600+ words)."
    }
    
    if length in length_guidance:
        base_prompt += length_guidance[length]
    
    return base_prompt

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/models', methods=['GET'])
def get_models():
    """Get available models"""
    return jsonify(MODELS)

@app.route('/api/prompts', methods=['GET'])
def get_prompts():
    """Get writing prompts and tones"""
    return jsonify({
        'prompts': WRITING_PROMPTS,
        'tones': TONES
    })

@app.route('/api/generate', methods=['POST'])
def generate_text():
    """Generate text without streaming"""
    data = request.json
    
    user_input = data.get('input', '')
    model = data.get('model', 'llama-3.1-8b-instant')
    writing_type = data.get('type', 'creative')
    tone = data.get('tone', 'professional')
    length = data.get('length', 'medium')
    temperature = data.get('temperature', 0.7)
    
    if not user_input:
        return jsonify({'error': 'No input provided'}), 400
    
    try:
        # Create system prompt
        system_prompt = create_system_prompt(writing_type, tone, length)
        
        # Create user prompt
        if writing_type in WRITING_PROMPTS:
            user_prompt = WRITING_PROMPTS[writing_type] + user_input
        else:
            user_prompt = user_input
        
        # Generate completion
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=1024,
            top_p=1,
            stream=False
        )
        
        response_text = completion.choices[0].message.content
        
        return jsonify({
            'success': True,
            'text': response_text,
            'model': model,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate_stream', methods=['POST'])
def generate_stream():
    """Generate text with streaming"""
    data = request.json
    
    user_input = data.get('input', '')
    model = data.get('model', 'llama-3.1-8b-instant')
    writing_type = data.get('type', 'creative')
    tone = data.get('tone', 'professional')
    length = data.get('length', 'medium')
    temperature = data.get('temperature', 0.7)
    
    if not user_input:
        return jsonify({'error': 'No input provided'}), 400
    
    def generate():
        try:
            # Create system prompt
            system_prompt = create_system_prompt(writing_type, tone, length)
            
            # Create user prompt
            if writing_type in WRITING_PROMPTS:
                user_prompt = WRITING_PROMPTS[writing_type] + user_input
            else:
                user_prompt = user_input
            
            # Generate streaming completion
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=1024,
                top_p=1,
                stream=True,
                stop=None
            )
            
            # Send start signal
            yield f"data: {json.dumps({'type': 'start', 'model': model})}\n\n"
            
            # Stream tokens
            for chunk in completion:
                if chunk.choices[0].delta.content:
                    token_data = {
                        'type': 'token',
                        'content': chunk.choices[0].delta.content
                    }
                    yield f"data: {json.dumps(token_data)}\n\n"
            
            # Send end signal
            yield f"data: {json.dumps({'type': 'end', 'timestamp': datetime.now().isoformat()})}\n\n"
            
        except Exception as e:
            error_data = {'type': 'error', 'error': str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/improve', methods=['POST'])
def improve_text():
    """Improve existing text"""
    data = request.json
    
    text = data.get('text', '')
    improvement_type = data.get('type', 'grammar')
    model = data.get('model', 'llama-3.1-8b-instant')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    try:
        improvement_prompts = {
            'grammar': 'Fix grammar, spelling, and punctuation errors in the following text. Maintain the original meaning and style:',
            'style': 'Improve the writing style and flow of the following text while keeping the same meaning:',
            'clarity': 'Rewrite the following text to be clearer and more concise:',
            'formal': 'Rewrite the following text in a more formal tone:',
            'casual': 'Rewrite the following text in a more casual, friendly tone:'
        }
        
        prompt = improvement_prompts.get(improvement_type, improvement_prompts['grammar'])
        
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert editor and writing assistant."},
                {"role": "user", "content": f"{prompt}\n\n{text}"}
            ],
            temperature=0.3,
            max_tokens=1024,
            top_p=1,
            stream=False
        )
        
        improved_text = completion.choices[0].message.content
        
        return jsonify({
            'success': True,
            'original': text,
            'improved': improved_text,
            'type': improvement_type,
            'model': model
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    """Analyze text for various metrics"""
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    try:
        # Basic text analysis
        word_count = len(text.split())
        char_count = len(text)
        char_count_no_spaces = len(text.replace(' ', ''))
        sentence_count = len([s for s in text.split('.') if s.strip()])
        paragraph_count = len([p for p in text.split('\n\n') if p.strip()])
        
        # Readability estimate (simple)
        avg_words_per_sentence = word_count / max(sentence_count, 1)
        
        # Get AI analysis
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a writing analyst. Provide a brief analysis of the text's tone, style, and suggestions for improvement."},
                {"role": "user", "content": f"Analyze this text:\n\n{text}"}
            ],
            temperature=0.3,
            max_tokens=512,
            stream=False
        )
        
        ai_analysis = completion.choices[0].message.content
        
        return jsonify({
            'success': True,
            'metrics': {
                'word_count': word_count,
                'character_count': char_count,
                'character_count_no_spaces': char_count_no_spaces,
                'sentence_count': sentence_count,
                'paragraph_count': paragraph_count,
                'avg_words_per_sentence': round(avg_words_per_sentence, 1)
            },
            'ai_analysis': ai_analysis
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)