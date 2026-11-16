"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  X,
  Send,
  Bot,
  User,
  Terminal,
  RotateCcw,
  Maximize2,
  Minimize2,
} from "lucide-react";

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  toolsCalled?: string[];
  timestamp: string;
}

const INITIAL_MESSAGES: Message[] = [
  {
    id: "welcome-1",
    sender: "assistant",
    text: `**Welcome to Verilumen ATE Copilot!**\n\nConnected to all ATE AI engines via **MCP (Model Context Protocol)**:\n* **Dynamic Limits (DTL)** — Cpk guardband tightening & relaxation\n* **Log Analyzer** — Adaptive scan pattern ranking & diagnostics\n* **M-BIST Shmoo** — Voltage speedpath boundary & operational headroom\n* **RA Advisor** — Memory built-in self-repair & spare allocation\n* **Retest AI** — Recovery probability & root-cause feature attribution\n* **STIL Setup** — STIL syntax analysis & CUDA clock deskew\n* **Vector Memory** — LSTM STIL scan vector compression & time savings\n* **Yield Advisor** — FPY Pareto recovery & wafer spatial analytics\n\nClick any prompt below or type your question!`,
    timestamp: "Just now",
  },
];

const SUGGESTED_PROMPTS = [
  { label: "Shmoo Parameters & Analysis", query: "what are the parameters used to generate the shmoo plot and how the analysis is done here" },
  { label: "Full Wafer Audit", query: "Audit current wafer across all models and summarize the findings" },
  { label: "Why Retest SKIP?", query: "Why did Retest recommend SKIP? Show failure drivers" },
  { label: "Vector Savings", query: "How much test time did STIL vector compression save?" },
  { label: "DTL Guardbands", query: "Recommend dynamic test limits for the current wafer lot" },
  { label: "STIL Timing & Clocks", query: "Optimize STIL timing setup and minimize clock skew with CUDA GBC" },
  { label: "Yield Recovery & Pareto", query: "Audit First Pass Yield and failure bin Pareto distribution" },
  { label: "Log Analyzer Patterns", query: "Audit scan pattern failure probabilities and adaptive log analyzer rankings" },
];

function FormattedMarkdown({ content }: { content: string }) {
  // Sanitize text to remove raw LaTeX math delimiters and escaped text
  const cleanLatex = (raw: string) => {
    return raw
      .replace(/\t/g, " ")
      .replace(/\\text\{([^}]+)\}/g, "$1") // \text{ V} -> V
      .replace(/\\ext\{([^}]+)\}/g, "$1")  // broken \t -> ext{ V} -> V
      .replace(/\$([^\$]+)\$/g, "$1")      // $0.975 V$ -> 0.975 V
      .replace(/_\{([^}]+)\}/g, "$1")      // C_{pk} -> Cpk
      .replace(/\\Delta/g, "Δ")
      .replace(/\\sigma/g, "σ");
  };

  const parseInline = (text: string) => {
    const sanitized = cleanLatex(text);
    const parts = sanitized.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`)/g);
    return parts.map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
        return (
          <strong key={index} className="font-semibold text-white tracking-wide">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("*") && part.endsWith("*") && part.length >= 2 && !part.startsWith("**")) {
        return (
          <em key={index} className="italic text-slate-300">
            {part.slice(1, -1)}
          </em>
        );
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
        return (
          <code
            key={index}
            className="rounded bg-cyan-950/70 border border-cyan-800/40 px-1.5 py-0.5 font-mono text-[11px] text-cyan-300"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
  };

  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeBlockLines: string[] = [];

  lines.forEach((line, lineIdx) => {
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        elements.push(
          <pre
            key={`code-${lineIdx}`}
            className="my-2 overflow-x-auto rounded-lg border border-slate-700/60 bg-slate-950/80 p-3 font-mono text-[11px] text-cyan-200"
          >
            <code>{codeBlockLines.join("\n")}</code>
          </pre>
        );
        codeBlockLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      return;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      return;
    }

    const trimmed = line.trim();
    if (!trimmed) {
      elements.push(<div key={`empty-${lineIdx}`} className="h-1.5" />);
      return;
    }

    // Match any Markdown header level (# through ######) and strip hashtags completely
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const title = headingMatch[2];
      if (level === 1) {
        elements.push(
          <h2 key={`h2-${lineIdx}`} className="mt-2.5 mb-1 text-[14px] font-extrabold text-white">
            {parseInline(title)}
          </h2>
        );
      } else if (level === 2) {
        elements.push(
          <h3 key={`h3-${lineIdx}`} className="mt-2 mb-1 text-[13px] font-bold text-cyan-200">
            {parseInline(title)}
          </h3>
        );
      } else {
        elements.push(
          <h4 key={`h4-${lineIdx}`} className="mt-1.5 mb-0.5 text-[12.5px] font-bold text-cyan-300">
            {parseInline(title)}
          </h4>
        );
      }
      return;
    }

    // Bullet list items (*, -, •)
    if (trimmed.startsWith("* ") || trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
      const itemText = trimmed.replace(/^[\*\-•]\s+/, "");
      elements.push(
        <div key={`li-${lineIdx}`} className="flex items-start gap-2 my-1 pl-1">
          <span className="text-cyan-400 mt-1 text-[10px] leading-none">•</span>
          <span className="flex-1 text-slate-200">{parseInline(itemText)}</span>
        </div>
      );
      return;
    }

    // Numbered list items (1., 2., 1), 2))
    const numMatch = trimmed.match(/^(\d+[\.)])\s+(.*)$/);
    if (numMatch) {
      elements.push(
        <div key={`oli-${lineIdx}`} className="flex items-start gap-2 my-1 pl-1">
          <span className="text-cyan-400 font-mono text-[11px] font-semibold">{numMatch[1]}</span>
          <span className="flex-1 text-slate-200">{parseInline(numMatch[2])}</span>
        </div>
      );
      return;
    }

    // Standard paragraph
    elements.push(
      <p key={`p-${lineIdx}`} className="my-1 leading-relaxed">
        {parseInline(line)}
      </p>
    );
  });

  return <div className="space-y-0.5 text-[12.5px] leading-relaxed">{elements}</div>;
}

interface AICopilotDrawerProps {
  mode?: "drawer" | "docked";
  onClose?: () => void;
}

export function AICopilotDrawer({ mode = "drawer", onClose }: AICopilotDrawerProps) {
  const [isOpen, setIsOpen] = useState(mode === "docked");
  const [isExpanded, setIsExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  // Listen for programmatic open events from other screens
  useEffect(() => {
    const handleOpenCopilot = (e: Event) => {
      const customEvent = e as CustomEvent<{ query?: string }>;
      setIsOpen(true);
      if (customEvent.detail?.query) {
        handleSend(customEvent.detail.query);
      }
    };

    window.addEventListener("openCopilot", handleOpenCopilot);
    return () => window.removeEventListener("openCopilot", handleOpenCopilot);
  }, []);

  const handleSend = async (textToSend?: string) => {
    const query = (textToSend || inputValue).trim();
    if (!query || loading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputValue("");
    setLoading(true);

    try {
      const res = await fetch("/api/mcp/copilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "assistant",
        text: data.reply || "Analysis completed.",
        toolsCalled: data.tools_called || [],
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "assistant",
        text: `Unable to reach the ATE Central Intelligence services. Ensure the suite is running via \`run_suite.py\`.`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  if (mode === "docked") {
    return (
      <div className="flex h-full w-full flex-col rounded-xl border border-[var(--line,#1e293b)] bg-[var(--panel,#0c121b)] shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--line,#1e293b)] px-5 py-4 bg-[var(--panel-2,#08101a)]">
          <div>
            <h3 className="text-sm font-bold text-white tracking-wide">
              Verilumen ATE Copilot
            </h3>
          </div>

          <div className="flex items-center gap-2 text-slate-400">
            <button
              onClick={() => setMessages(INITIAL_MESSAGES)}
              className="rounded-lg p-1.5 hover:bg-white/10 hover:text-white transition-colors"
              title="Reset conversation"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
            {onClose && (
              <button
                onClick={onClose}
                className="flex items-center gap-1.5 rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] px-3 py-1 text-xs font-medium text-slate-300 hover:text-white hover:border-slate-600 transition-colors"
                title="Close AI Copilot"
              >
                <X className="h-3.5 w-3.5" />
                <span>Close</span>
              </button>
            )}
          </div>
        </div>

        {/* Quick Action Suggestion Bar */}
        <div className="flex items-center gap-2 overflow-x-auto border-b border-[var(--line,#1e293b)] px-4 py-2.5 bg-[var(--panel-2,#08101a)] no-scrollbar">
          {SUGGESTED_PROMPTS.map((item, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(item.query)}
              className="whitespace-nowrap rounded-lg border border-[var(--line,#1a2433)] bg-[var(--panel,#0c121b)] px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:border-slate-600 hover:text-white"
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.sender === "assistant" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] text-cyan-400">
                  <Bot className="h-4 w-4" />
                </div>
              )}

              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed space-y-2 ${
                  msg.sender === "user"
                    ? "bg-cyan-700/80 text-white rounded-tr-none shadow-sm"
                    : "bg-[var(--panel-2,#08101a)] text-slate-200 border border-[var(--line,#1e293b)] rounded-tl-none shadow-sm"
                }`}
              >

                <div className="font-sans text-sm leading-relaxed">
                  <FormattedMarkdown content={msg.text} />
                </div>

                <div
                  className={`text-xs text-right ${
                    msg.sender === "user" ? "text-cyan-200" : "text-slate-500"
                  }`}
                >
                  {msg.timestamp}
                </div>
              </div>

              {msg.sender === "user" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-800 border border-slate-700 text-slate-300">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--panel-2,#08101a)] border border-[var(--line,#1a2433)] text-cyan-400">
                <Bot className="h-4 w-4" />
              </div>
              <div className="flex items-center gap-2 rounded-2xl rounded-tl-none border border-[var(--line,#1e293b)] bg-[var(--panel-2,#08101a)] px-4 py-2.5 text-xs text-cyan-300">
                <span className="h-2 w-2 rounded-full bg-cyan-400" />
                <span>Invoking live ATE microservices via MCP...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Box */}
        <div className="border-t border-[var(--line,#1e293b)] p-4 bg-[var(--panel-2,#08101a)]">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-2.5 rounded-xl border border-[var(--line,#1e293b)] bg-[var(--panel,#0c121b)] px-3.5 py-2 focus-within:border-cyan-500/50 transition-colors"
          >
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask about Shmoo, STIL vectors, Cpk limits, RA repair, or Retest..."
              className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || loading}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-600 text-white transition-all hover:bg-cyan-500 disabled:opacity-30"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    );
  }


  return (
    <>
      {/* Floating Action Button (FAB) */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full border border-[var(--line-bright,#2c3a50)] bg-[var(--panel,#0c121b)] px-4 py-2.5 text-sm font-semibold text-white shadow-xl backdrop-blur-md transition-all hover:bg-[var(--panel-2,#08101a)] hover:border-slate-500 group"
          title="Open Verilumen AI Copilot"
        >
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/25">
            <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
          </div>
          <span className="tracking-wide">AI Copilot</span>
        </button>
      )}

      {/* Slide-over Drawer */}
      {isOpen && (
        <div
          className={`fixed bottom-0 right-0 z-50 flex flex-col border-l border-[var(--line,#1e293b)] bg-[var(--panel,#0c121b)] shadow-2xl transition-all duration-200 ${
            isExpanded
              ? "inset-y-0 w-full md:w-[760px]"
              : "inset-y-0 w-full sm:w-[500px]"
          }`}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[var(--line,#1e293b)] px-5 py-4 bg-[var(--panel-2,#08101a)]">
            <div>
              <h3 className="text-sm font-bold text-white tracking-wide">
                Verilumen ATE Copilot
              </h3>
            </div>

            <div className="flex items-center gap-1 text-slate-400">
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="hidden sm:inline-flex rounded-lg p-1.5 hover:bg-white/10 hover:text-white transition-colors"
                title={isExpanded ? "Collapse width" : "Expand width"}
              >
                {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                onClick={() => setMessages(INITIAL_MESSAGES)}
                className="rounded-lg p-1.5 hover:bg-white/10 hover:text-white transition-colors"
                title="Reset conversation"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1.5 hover:bg-white/10 hover:text-white transition-colors"
                title="Close Copilot"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Quick Action Suggestion Bar */}
          <div className="flex items-center gap-1.5 overflow-x-auto border-b border-[var(--line,#1e293b)] px-4 py-2.5 bg-[rgba(13,20,35,0.4)] no-scrollbar">
            {SUGGESTED_PROMPTS.map((item, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(item.query)}
                className="whitespace-nowrap rounded-lg border border-slate-800 bg-slate-900/60 px-2.5 py-1 text-[11px] font-medium text-slate-300 transition-all hover:border-cyan-500/30 hover:bg-cyan-500/10 hover:text-cyan-200"
              >
                {item.label}
              </button>
            ))}
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.sender === "assistant" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-950/50 border border-cyan-800/40 text-cyan-400">
                    <Bot className="h-4 w-4" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed space-y-2 ${
                    msg.sender === "user"
                      ? "bg-cyan-600 text-white rounded-tr-none shadow-[0_4px_15px_rgba(6,182,212,0.25)]"
                      : "bg-[rgba(18,27,45,0.7)] text-slate-200 border border-[var(--line,#1e293b)] rounded-tl-none shadow-sm"
                  }`}
                >
                  

                  <div className="font-sans text-[12.5px] leading-relaxed">
                    <FormattedMarkdown content={msg.text} />
                  </div>

                  <div
                    className={`text-[10px] text-right ${
                      msg.sender === "user" ? "text-cyan-100" : "text-slate-500"
                    }`}
                  >
                    {msg.timestamp}
                  </div>
                </div>

                {msg.sender === "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-800 border border-slate-700 text-slate-300">
                    <User className="h-4 w-4" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-950/50 border border-cyan-800/40 text-cyan-400">
                  <Bot className="h-4 w-4" />
                </div>
                <div className="flex items-center gap-2 rounded-2xl rounded-tl-none border border-[var(--line,#1e293b)] bg-[rgba(18,27,45,0.7)] px-4 py-3 text-xs text-cyan-300">
                  <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
                  <span>Invoking live ATE microservices via MCP...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Box */}
          <div className="border-t border-[var(--line,#1e293b)] p-4 bg-[rgba(13,20,35,0.85)]">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-center gap-2 rounded-xl border border-[var(--line,#1e293b)] bg-[rgba(18,28,48,0.6)] px-3 py-2 focus-within:border-cyan-500/50 focus-within:ring-1 focus-within:ring-cyan-500/30 transition-all"
            >
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Ask about Shmoo, STIL vectors, Cpk limits, or Retest..."
                className="flex-1 bg-transparent text-xs text-white placeholder-slate-500 focus:outline-none"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={!inputValue.trim() || loading}
                className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-500 text-slate-950 transition-all hover:bg-cyan-400 disabled:opacity-30 disabled:hover:bg-cyan-500"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}