import { useEffect, useRef, useState, useCallback } from 'react';
import clsx from 'clsx';
import { MessageSquare, X, Send, BookOpen, Sparkles, Loader2, ChevronDown } from 'lucide-react';

type Citation = {
  chapter: number | null;
  chapter_title: string;
  section: string;
  score: number;
  text: string;
};

type Message = {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  source?: 'ollama' | 'extractive';
  ts: number;
};

const SUGGESTED = [
  'Why is Brent moving today?',
  'Explain backwardation vs contango',
  'What does the 3-2-1 crack tell us?',
  'How would the curriculum read today\'s setup?',
  'What\'s the bull case for Brent right now?',
  'Why does Hormuz matter for oil prices?',
];

async function askApi(question: string): Promise<{
  answer: string;
  citations: Citation[];
  source: string;
}> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const j = await res.json();
  return j.data ?? j;
}

function renderMarkdown(text: string): string {
  // Tiny, safe markdown: bold + italic + line breaks + simple inline code
  let out = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  out = out.replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 bg-bg-elev rounded text-gold">$1</code>');
  out = out.replace(/\[Ch(\d+)\]/g, '<span class="inline-block px-1 py-0.5 bg-gold-soft text-gold rounded text-[9px] font-mono tracking-wider">Ch$1</span>');
  out = out.replace(/\n/g, '<br/>');
  return out;
}

function CitationCard({ c, idx }: { c: Citation; idx: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-bg-elev/60 border border-border/60 rounded text-[10.5px]">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-bg-hover/40"
      >
        <span className="text-[9px] font-mono text-gold font-semibold">[{idx + 1}]</span>
        <span className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary flex-shrink-0">
          {c.chapter ? `Ch${c.chapter}` : 'Ch?'}
        </span>
        <span className="text-text-secondary truncate flex-1 text-left">
          {c.chapter_title} · {c.section}
        </span>
        <span className="text-[9px] font-mono text-text-muted">{c.score.toFixed(1)}</span>
        <ChevronDown className={clsx('w-3 h-3 text-text-muted transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="px-2 pb-2 text-[10px] text-text-tertiary leading-relaxed border-t border-border/40">
          {c.text}
        </div>
      )}
    </div>
  );
}

export function ChatDock() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Focus on open
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  // Slash key opens chat (when not typing in another input)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === '/') {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const submit = useCallback(async (question: string) => {
    if (!question.trim() || loading) return;
    const user: Message = { role: 'user', content: question, ts: Date.now() };
    setMessages(m => [...m, user]);
    setInput('');
    setLoading(true);
    try {
      const r = await askApi(question);
      setMessages(m => [...m, {
        role: 'assistant',
        content: r.answer,
        citations: r.citations,
        source: r.source as any,
        ts: Date.now(),
      }]);
    } catch (e: any) {
      setMessages(m => [...m, {
        role: 'assistant',
        content: `⚠ Failed to reach /api/ask: ${e.message ?? e}. Make sure Flask is running.`,
        ts: Date.now(),
      }]);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  // Floating button when closed
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-9 right-5 z-50 flex items-center gap-2 px-4 py-3 bg-gradient-to-br from-gold to-gold-bright text-bg rounded-full shadow-lg shadow-gold/40 hover:scale-105 transition-all"
        title="Ask PULSE (/)"
      >
        <MessageSquare className="w-4 h-4" strokeWidth={2.5} />
        <span className="font-display font-bold tracking-widest text-xs uppercase">Ask PULSE</span>
        <kbd className="text-[9px] font-mono bg-bg/30 px-1.5 py-0.5 rounded">/</kbd>
      </button>
    );
  }

  return (
    <div className="fixed bottom-9 right-5 z-50 w-[420px] max-w-[calc(100vw-32px)] h-[600px] max-h-[calc(100vh-100px)] flex flex-col bg-bg-surface border border-border rounded-lg shadow-2xl animate-fade-in">
      {/* gold top accent */}
      <div
        aria-hidden
        className="absolute inset-x-3 top-0 h-px pointer-events-none"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(212,175,55,0.6), transparent)' }}
      />

      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/70">
        <Sparkles className="w-4 h-4 text-gold" />
        <div className="flex-1 min-w-0">
          <div className="font-display font-bold tracking-widest text-sm uppercase">Ask PULSE</div>
          <div className="text-[10px] font-mono text-text-tertiary">
            grounded in OilMacroTrading curriculum + live data
          </div>
        </div>
        <button
          onClick={() => setOpen(false)}
          className="p-1.5 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-hover"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <BookOpen className="w-3.5 h-3.5 text-text-tertiary" />
              <span className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">
                Try asking
              </span>
            </div>
            <div className="grid grid-cols-1 gap-1.5">
              {SUGGESTED.map(s => (
                <button
                  key={s}
                  onClick={() => submit(s)}
                  className="text-left text-[11px] px-3 py-2 bg-bg-card/50 hover:bg-bg-hover/60 border border-border/40 hover:border-gold/40 rounded text-text-secondary hover:text-text-primary transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
            <div className="mt-4 text-[10px] font-mono text-text-muted text-center">
              <kbd className="px-1.5 py-0.5 bg-bg-elev rounded">/</kbd> opens this chat ·{' '}
              <kbd className="px-1.5 py-0.5 bg-bg-elev rounded">Esc</kbd> closes
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={clsx('flex flex-col', m.role === 'user' ? 'items-end' : 'items-start')}>
            <div
              className={clsx(
                'max-w-[92%] px-3 py-2 rounded-lg text-[12px] leading-relaxed',
                m.role === 'user'
                  ? 'bg-gold/15 text-text-primary border border-gold/30'
                  : 'bg-bg-card/60 text-text-secondary border border-border/40',
              )}
            >
              {m.role === 'assistant' ? (
                <div
                  className="prose-tight"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}
                />
              ) : (
                m.content
              )}
              {m.role === 'assistant' && m.source && (
                <div className="mt-2 pt-2 border-t border-border/40 flex items-center gap-2 text-[9px] font-mono uppercase tracking-widest text-text-muted">
                  <span className={clsx(
                    'inline-block w-1.5 h-1.5 rounded-full',
                    m.source === 'ollama' ? 'bg-bull' : 'bg-neut',
                  )} />
                  {m.source === 'ollama' ? 'LLM · llama3' : 'extractive (Ollama offline)'}
                </div>
              )}
            </div>
            {m.role === 'assistant' && m.citations && m.citations.length > 0 && (
              <div className="mt-2 w-full max-w-[92%] space-y-1">
                <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted px-1">
                  Citations
                </div>
                {m.citations.map((c, idx) => <CitationCard key={idx} c={c} idx={idx} />)}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-start">
            <div className="bg-bg-card/60 border border-border/40 rounded-lg px-3 py-2 flex items-center gap-2 text-[11px] font-mono text-text-tertiary">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              thinking… (curriculum lookup + live snapshot)
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border/70 p-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about markets, indicators, contracts…"
            rows={1}
            className="flex-1 resize-none bg-bg-elev border border-border rounded px-3 py-2 text-[12px] font-sans text-text-primary placeholder:text-text-muted focus:border-gold/50 focus:outline-none max-h-32"
            disabled={loading}
          />
          <button
            onClick={() => submit(input)}
            disabled={loading || !input.trim()}
            className="p-2 rounded bg-gold text-bg hover:bg-gold-bright disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            aria-label="Send"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" strokeWidth={2.5} />}
          </button>
        </div>
        <div className="mt-1.5 text-[9px] font-mono text-text-muted text-right">
          Enter to send · Shift+Enter for newline
        </div>
      </div>
    </div>
  );
}
