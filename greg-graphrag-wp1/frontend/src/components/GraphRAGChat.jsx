import React, { useState, useEffect, useRef } from 'react';
import { Spinner, Tooltip, Dropdown, DropdownHeader, DropdownItem } from 'flowbite-react';
import {
  HiPaperAirplane,
  HiChatAlt2,
  HiStop,
  HiPlus,
  HiMenuAlt2,
  HiTrash,
  HiThumbUp,
  HiThumbDown,
  HiChevronDown
} from 'react-icons/hi';
import ReactMarkdown from 'react-markdown';

const generateId = () => crypto.randomUUID();

export default function GraphRAGChat() {

  const API_URL = import.meta.env.PUBLIC_API_URL || '/api';

  const [userId] = useState(() => {
    const saved = localStorage.getItem('graphrag_user_id');
    if (saved) return saved;
    const newId = `user-${generateId()}`;
    localStorage.setItem('graphrag_user_id', newId);
    return newId;
  });

  const [sessionId, setSessionId] = useState(() => generateId());

  const [input, setInput] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [history, setHistory] = useState([]);
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Hello. I am your **GraphRAG Strategic Advisor**. \n\nHow can I assist you today?`,
    }
  ]);

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [chatToDelete, setChatToDelete] = useState(null);

  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);
  const wordQueueRef = useRef([]);
  const typingIntervalRef = useRef(null);

  useEffect(() => {
    loadSidebarHistory();
    return () => stopTypingEngine();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const startTypingEngine = (botMsgId) => {
    if (typingIntervalRef.current) return;
    typingIntervalRef.current = setInterval(() => {
      if (wordQueueRef.current.length > 0) {
        const nextPart = wordQueueRef.current.shift();
        setMessages(prev => prev.map(msg => {
          if (msg.id === botMsgId) {
            return { ...msg, content: msg.content + nextPart };
          }
          return msg;
        }));
      }
    }, 20);
  };

  const stopTypingEngine = () => {
    if (typingIntervalRef.current) {
      clearInterval(typingIntervalRef.current);
      typingIntervalRef.current = null;
    }
  };

  const loadSidebarHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/sessions/${userId}`);
      const data = await response.json();
      setHistory(data);
    } catch (error) {
      console.error("Error loading sidebar history:", error);
    }
  };

  const loadHistoryChat = async (histId) => {
    stopTypingEngine();
    setIsProcessing(true);
    try {
      const response = await fetch(`${API_URL}/history/${histId}`);
      const data = await response.json();
      if (data.messages) {
        setSessionId(histId);
        setMessages(data.messages);
      }
    } catch (error) {
      console.error("Error loading chat context:", error);
    } finally {
      setIsProcessing(false);
      if (window.innerWidth < 768) setIsSidebarOpen(false);
    }
  };

  const startNewChat = () => {
    stopTypingEngine();
    const newId = generateId();
    setSessionId(newId);
    setMessages([{
      id: 'welcome-' + Date.now(),
      role: 'assistant',
      content: "Ready for a new strategic analysis. What's on your mind?"
    }]);
    setIsProcessing(false);
  };

  const sendFeedback = async (messageId, voteValue, reason = null) => {
    try {
      const response = await fetch(`${API_URL}/chat/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: messageId,
          vote: voteValue,
          reason: reason
        }),
      });

      if (response.ok) {
        setMessages(prev => prev.map(msg =>
          msg.id === messageId ? { ...msg, voted: voteValue } : msg
        ));
      }
    } catch (error) {
      console.error("Error sending feedback:", error);
    }
  };

  const openDeleteModal = (e, histId) => {
    e.stopPropagation();
    setChatToDelete(histId);
    setShowDeleteModal(true);
  };

  const confirmDelete = async () => {
    if (!chatToDelete) return;
    try {
      const response = await fetch(`${API_URL}/sessions/${chatToDelete}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        if (sessionId === chatToDelete) startNewChat();
        loadSidebarHistory();
      }
    } catch (error) {
      console.error("Error deleting session:", error);
    } finally {
      setShowDeleteModal(false);
      setChatToDelete(null);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || isProcessing) return;

    const userText = input;
    setInput('');
    setIsProcessing(true);

    const userMsgId = `user-${Date.now()}`;
    const botMsgId = `msg-${generateId()}`;
    wordQueueRef.current = [];

    setMessages(prev => [
      ...prev,
      { id: userMsgId, role: 'user', content: userText },
      { id: botMsgId, role: 'assistant', content: '' }
    ]);

    startTypingEngine(botMsgId);

    try {
      abortControllerRef.current = new AbortController();
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userText,
          session_id: sessionId,
          user_id: userId,
          message_id: botMsgId
        }),
        signal: abortControllerRef.current.signal
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let partialWord = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const parts = (partialWord + chunk).split(/(\n| +)/);
        partialWord = parts.pop() || "";
        if (parts.length > 0) {
          wordQueueRef.current.push(...parts);
        }
      }
      if (partialWord) wordQueueRef.current.push(partialWord);
      loadSidebarHistory();

    } catch (error) {
      if (error.name !== 'AbortError') {
        stopTypingEngine();
        setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, content: m.content + " [System Error: Connection failed]" } : m));
      }
    } finally {
      setIsProcessing(false);
      abortControllerRef.current = null;
      const checkEnd = setInterval(() => {
        if (wordQueueRef.current.length === 0) {
          stopTypingEngine();
          clearInterval(checkEnd);
        }
      }, 500);
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsProcessing(false);
      stopTypingEngine();
    }
  };

  return (
    <div className="flex h-screen bg-[#fcfaf8] font-sans overflow-hidden relative text-[#3b1c1c]">

      {/* SIDEBAR */}
      <aside className={`fixed md:relative z-30 h-full w-64 bg-[#e8ded4] border-r border-[#d8ccc0] flex flex-col transition-all duration-300 ease-in-out ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0 md:-ml-64'}`}>
        <div className="p-4">
          <button onClick={startNewChat} className="w-full flex items-center gap-3 px-4 py-3 bg-[#3b1c1c] hover:bg-[#522a2a] text-[#e8ded4] rounded-xl transition-all text-sm font-medium shadow-md group">
            <HiPlus className="w-5 h-5 text-[#fc8f5c] group-hover:rotate-90 transition-transform duration-300" />
            <span>New Chat</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 custom-scrollbar">
          <p className="px-3 text-[10px] font-bold text-[#3b1c1c]/60 mb-2 uppercase tracking-[0.15em]">Cloud History</p>
          <ul className="space-y-1">
            {history.map((chat) => (
              <li key={chat.id} className="group relative">
                <button
                  onClick={() => loadHistoryChat(chat.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm flex items-center gap-3 transition-all pr-10 ${sessionId === chat.id ? 'bg-[#3b1c1c] text-[#e8ded4] shadow-sm' : 'text-[#3b1c1c] hover:bg-[#d8ccc0]'}`}
                >
                  <HiChatAlt2 className={`w-4 h-4 flex-shrink-0 ${sessionId === chat.id ? 'text-[#fc8f5c]' : 'text-[#3b1c1c]/40'}`} />
                  <span className="truncate">{chat.title || "Untitled Analysis"}</span>
                </button>
                <button
                  onClick={(e) => openDeleteModal(e, chat.id)}
                  className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md transition-all ${sessionId === chat.id ? 'text-[#fc8f5c] hover:bg-[#fc8f5c]/20' : 'text-[#3b1c1c]/30 hover:text-red-600 hover:bg-red-50 opacity-0 group-hover:opacity-100'}`}
                >
                  <HiTrash className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="p-4 border-t border-[#d8ccc0]">
          <div className="bg-[#d8ccc0]/40 p-3 rounded-lg text-[10px] font-mono flex justify-between items-center">
            <span className="text-[#3b1c1c]/60 uppercase">System Status:</span>
            <span className="flex items-center gap-1.5 text-[#3b1c1c] font-bold">
              <span className="w-2 h-2 bg-[#61fc5c] rounded-full animate-pulse"></span> LIVE
            </span>
          </div>
        </div>
      </aside>

      {/* MAIN AREA */}
      <main className="flex-1 flex flex-col min-w-0 relative z-10 h-full">
        <header className="h-24 flex items-center justify-between px-8 border-b border-[#e8ded4] flex-shrink-0 bg-white/80 backdrop-blur-md">
          <div className="flex items-center gap-6">
            <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 text-[#3b1c1c] hover:bg-[#e8ded4] rounded-lg transition-colors">
              <HiMenuAlt2 className="w-7 h-7" />
            </button>
            <div className="flex items-center gap-4">
              <img src="/Greg_Logo_Horizontal_RGB_Berry.png" alt="Logo" className="h-14 w-auto object-contain" />
              <div className="h-6 w-[1px] bg-[#e8ded4]"></div>
              <span className="text-[#fc8f5c] font-bold text-[10px] bg-[#fc8f5c]/10 border border-[#fc8f5c]/20 px-3 py-1 rounded-full uppercase tracking-widest">Advisor</span>
            </div>
          </div>
        </header>

        {/* MESSAGES */}
        <div className="flex-1 overflow-y-auto p-6 scroll-smooth custom-scrollbar">
          <div className="max-w-5xl mx-auto space-y-8 pb-4">
            {messages.map((msg, index) => {
              const isLastMessage = index === messages.length - 1;
              const isBot = msg.role === 'assistant';
              const msgIdStr = (msg.id || '').toString();

              const canShowFeedback =
                !isProcessing &&
                isBot &&
                isLastMessage &&
                msgIdStr !== '' &&
                !msgIdStr.startsWith('welcome');

              return (
                <div key={msg.id} className={`flex gap-5 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                  {isBot && (
                    <div className="w-10 h-10 flex-shrink-0 mt-1">
                      <img src="/logo2_GREG.png" alt="AI" className="w-full rounded-xl object-cover border-2 border-[#e8ded4] shadow-sm" />
                    </div>
                  )}
                  <div className={`flex-1 min-w-0 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                    <div className="relative inline-block max-w-full">
                      <div className={`inline-block text-sm leading-relaxed py-4 px-6 shadow-sm border ${msg.role === 'user'
                        ? 'bg-[#3b1c1c] text-[#e8ded4] rounded-2xl rounded-tr-none border-[#3b1c1c]'
                        : 'bg-[#e8ded4]/30 text-[#3b1c1c] border-[#e8ded4] prose prose-sm max-w-none rounded-2xl rounded-tl-none'
                        }`}>
                        <ReactMarkdown components={{
                          a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" className="text-[#fc8f5c] font-bold hover:underline" />,
                          strong: ({ node, ...props }) => <strong {...props} className="text-[#3b1c1c] font-extrabold" />
                        }}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>

                      {/* FEEDBACK COMPONENT */}
                      {canShowFeedback && (
                        <div className="absolute -bottom-10 left-0 flex items-center gap-2 animate-in fade-in slide-in-from-top-1 duration-500">
                          {!msg.voted ? (
                            <>
                              <button
                                onClick={() => sendFeedback(msg.id, 1)}
                                className="p-1.5 rounded-lg bg-white border border-[#d8ccc0] text-[#3b1c1c]/40 hover:text-green-600 hover:bg-green-50 transition-all shadow-sm group"
                              >
                                <HiThumbUp className="w-4 h-4 group-active:scale-125 transition-transform" />
                              </button>

                              <Dropdown
                                arrowIcon={false}
                                inline
                                label={
                                  <div className="p-1.5 rounded-lg bg-white border border-[#d8ccc0] text-[#3b1c1c]/40 hover:text-[#fc8f5c] hover:bg-[#fc8f5c]/5 hover:border-[#fc8f5c]/30 transition-all shadow-sm flex items-center gap-1 group">
                                    <HiThumbDown className="w-4 h-4 group-active:scale-125 transition-transform" />
                                    <HiChevronDown className="w-3 h-3" />
                                  </div>
                                }
                                theme={{
                                  content: "py-2 bg-[#fcfaf8] border border-[#d8ccc0] rounded-xl shadow-2xl min-w-[250px] z-50",
                                  item: {
                                    base: "flex w-full cursor-pointer items-center justify-start px-4 py-3 text-sm !text-[#3b1c1c] font-medium hover:bg-[#e8ded4] hover:text-[#3b1c1c] transition-colors",
                                  }
                                }}
                              >
                                <DropdownHeader className="border-b border-[#d8ccc0] bg-[#e8ded4]/20 py-3">
                                  <span className="block text-[10px] font-bold uppercase tracking-[0.2em] text-[#3b1c1c]/60">
                                    Report issue with analysis
                                  </span>
                                </DropdownHeader>

                                <div className="py-1">
                                  <DropdownItem onClick={() => sendFeedback(msg.id, -1, "Hallucination")}>
                                    <span className="w-2.5 h-2.5 rounded-full bg-[#fc8f5c] mr-3 shadow-sm"></span>
                                    Hallucination / False Info
                                  </DropdownItem>

                                  <DropdownItem onClick={() => sendFeedback(msg.id, -1, "Bad References")}>
                                    <span className="w-2.5 h-2.5 rounded-full bg-[#3b1c1c]/20 mr-3"></span>
                                    Incorrect References
                                  </DropdownItem>

                                  <DropdownItem onClick={() => sendFeedback(msg.id, -1, "Incomplete")}>
                                    <span className="w-2.5 h-2.5 rounded-full bg-[#3b1c1c]/20 mr-3"></span>
                                    Incomplete Analysis
                                  </DropdownItem>

                                  <DropdownItem onClick={() => sendFeedback(msg.id, -1, "Not Relevant")}>
                                    <span className="w-2.5 h-2.5 rounded-full bg-[#3b1c1c]/20 mr-3"></span>
                                    Irrelevant Content
                                  </DropdownItem>
                                </div>
                              </Dropdown>
                            </>
                          ) : (
                            <div className="flex items-center gap-2 bg-[#fc8f5c]/10 border border-[#fc8f5c]/30 px-3 py-1 rounded-md">
                              <span className="text-[9px] font-bold text-[#fc8f5c] uppercase tracking-widest">Analysis Feedback Received</span>
                              {msg.voted === 1 ? <HiThumbUp className="w-3 h-3 text-[#fc8f5c]" /> : <HiThumbDown className="w-3 h-3 text-[#fc8f5c]" />}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            {isProcessing && (
              <div className="flex items-center gap-3 px-2">
                <Spinner size="sm" color="warning" />
                <span className="text-[#3b1c1c]/50 text-xs font-medium animate-pulse tracking-wide italic">Synthesizing evidence...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* INPUT */}
        <div className="p-6 bg-white/50 backdrop-blur-sm border-t border-[#e8ded4]">
          <div className="max-w-5xl mx-auto">
            <form onSubmit={handleSend} className="relative flex items-center gap-3 bg-white border-2 border-[#e8ded4] rounded-2xl p-2.5 focus-within:border-[#fc8f5c] focus-within:shadow-xl transition-all shadow-sm">
              <input
                type="text"
                placeholder="Query strategic HTA evidence..."
                className="w-full bg-transparent border-none focus:ring-0 text-[#3b1c1c] px-4 py-3 placeholder-[#3b1c1c]/30"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={isProcessing && !abortControllerRef.current}
              />
              {isProcessing ? (
                <button type="button" onClick={handleStop} className="p-3 bg-[#e8ded4] hover:bg-[#fc8f5c] text-[#3b1c1c] rounded-xl transition-colors">
                  <HiStop className="w-6 h-6" />
                </button>
              ) : (
                <button type="submit" disabled={!input.trim()} className="p-3 bg-[#3b1c1c] hover:bg-[#fc8f5c] text-white rounded-xl disabled:opacity-20 transition-all shadow-lg active:scale-95">
                  <HiPaperAirplane className="w-6 h-6 rotate-90" />
                </button>
              )}
            </form>
          </div>
        </div>
      </main>

      {/* MODAL DE BORRADO LÓGICO */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-[#3b1c1c]/60 backdrop-blur-sm">
          <div className="bg-[#fcfaf8] w-full max-w-sm rounded-2xl shadow-2xl border border-[#e8ded4] overflow-hidden transform transition-all">
            <div className="p-6 text-center">
              <div className="w-16 h-16 bg-[#fc8f5c]/10 rounded-full flex items-center justify-center mx-auto mb-4">
                <HiTrash className="w-8 h-8 text-[#fc8f5c]" />
              </div>
              <h3 className="text-lg font-bold text-[#3b1c1c] mb-2">Archive Analysis?</h3>
              <p className="text-sm text-[#3b1c1c]/60 leading-relaxed">This action will remove the conversation from your active history. It will remain archived in the secure database.</p>
            </div>
            <div className="flex border-t border-[#e8ded4]">
              <button onClick={() => setShowDeleteModal(false)} className="flex-1 px-4 py-4 text-sm font-semibold text-[#3b1c1c]/60 hover:bg-[#e8ded4]/30 transition-colors border-r border-[#e8ded4]">Cancel</button>
              <button onClick={confirmDelete} className="flex-1 px-4 py-4 text-sm font-bold text-[#fc8f5c] hover:bg-[#fc8f5c]/10 transition-colors">Yes, Archive</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}