import { useState, useEffect, useRef } from 'react';
import { toast } from 'react-hot-toast';
import { v4 as uuidv4 } from 'uuid';
import { ResearchHistoryItem, Data, ChatMessage } from '../types/data';

export const useResearchHistory = () => {
  const [history, setHistory] = useState<ResearchHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const dataLoadedRef = useRef(false); // Track if data has been loaded
  
  // Fetch all research history on mount
  useEffect(() => {
    const controller=new AbortController();
    const load=async () => {
      let local:ResearchHistoryItem[]=[];
      try { const value=JSON.parse(localStorage.getItem('researchHistory') || '[]');if(Array.isArray(value))local=value; } catch { /* Use server history. */ }
      try {
        const response=await fetch('/api/reports?limit=50&offset=0',{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw new Error('History unavailable');
        const data=await response.json();
        if(!Array.isArray(data.reports))throw new Error('Invalid history response');
        if(controller.signal.aborted)return;
        setHistory(data.reports);
        // Preserve local-only legacy records for the explicit import action.
        const merged=new Map(local.map(item=>[item.id,item]));
        for(const item of data.reports)merged.set(item.id,item);
        try { localStorage.setItem('researchHistory',JSON.stringify(Array.from(merged.values()))); } catch { /* Server remains authoritative. */ }
      } catch {
        if(!controller.signal.aborted)setHistory(local.slice(0,50));
      } finally {
        if(!controller.signal.aborted){dataLoadedRef.current=true;setLoading(false);}
      }
    };
    void load();
    const refresh=()=>{void load();};
    window.addEventListener('tdr:history-changed',refresh);
    return ()=>{controller.abort();window.removeEventListener('tdr:history-changed',refresh);};
  }, []); // Empty dependency array - only run once on mount
  
  // Save new research
  const saveResearch = async (question: string, answer: string, orderedData: Data[]) => {
    try {
      // Generate a unique ID
      const id = uuidv4();
      
      // Save to backend
      const response = await fetch('/api/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          id,
          question,
          answer,
          orderedData,
          chatMessages: []
        }),
      });
      
      if (response.ok) {
        const data = await response.json();
        const newId = data.id;
        
        // Update local state
        const newResearch = {
          id: newId,
          question,
          answer,
          orderedData,
          chatMessages: [],
          timestamp: Date.now(),
        };
        
        setHistory(prev => [newResearch, ...prev]);
        
        // Also save to localStorage as fallback
        const localHistory = localStorage.getItem('researchHistory');
        const parsedHistory = localHistory ? JSON.parse(localHistory) : [];
        localStorage.setItem(
          'researchHistory',
          JSON.stringify([newResearch, ...parsedHistory])
        );
        
        return newId;
      } else {
        throw new Error(`API error: ${response.status}`);
      }
    } catch (error) {
      console.error('Error saving research:', error);
      toast.error("暂时无法保存到服务器，已保存在本机。");
      
      // Fallback: save to localStorage only
      const newResearch = {
        id: uuidv4(),
        question,
        answer,
        orderedData,
        chatMessages: [],
        timestamp: Date.now(),
      };
      
      // Update local state
      setHistory(prev => [newResearch, ...prev]);
      
      // Save to localStorage
      const localHistory = localStorage.getItem('researchHistory');
      const parsedHistory = localHistory ? JSON.parse(localHistory) : [];
      localStorage.setItem(
        'researchHistory',
        JSON.stringify([newResearch, ...parsedHistory])
      );
      
      return newResearch.id;
    }
  };
  
  // Update existing research
  const updateResearch = async (id: string, answer: string, orderedData: Data[]) => {
    try {
      // Update in backend
      const response = await fetch(`/api/reports/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          answer,
          orderedData
        }),
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      // Update local state
      setHistory(prev => 
        prev.map(item => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        )
      );
      
      // Also update localStorage as fallback
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        );
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return true;
    } catch (error) {
      console.error('Error updating research:', error);
      
      // Update local state anyway
      setHistory(prev => 
        prev.map(item => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        )
      );
      
      // Update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        );
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return false;
    }
  };

  // Get research by ID
  const getResearchById = async (id: string) => {
    try {
      const response = await fetch(`/api/reports/${id}`);
      if (response.ok) {
        const data = await response.json();
        return data.report;
      } else if (response.status === 404) {
        // If not found on server, try localStorage
        const localHistory = localStorage.getItem('researchHistory');
        if (localHistory) {
          const parsedHistory = JSON.parse(localHistory);
          return parsedHistory.find((item: any) => item.id === id) || null;
        }
      } else {
        throw new Error(`API error: ${response.status}`);
      }
    } catch (error) {
      console.error('Error getting research by ID:', error);
      
      // Try localStorage as fallback
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        return parsedHistory.find((item: any) => item.id === id) || null;
      }
      
      return null;
    }
  };

  // Delete research
  const deleteResearch = async (id: string) => {
    try {
      const response = await fetch(`/api/reports/${id}`, {
        method: 'DELETE',
      });
      
      if (!response.ok && response.status !== 404) {
        throw new Error(`API error: ${response.status}`);
      }
      
      // Update local state
      setHistory(prev => prev.filter(item => item.id !== id));
      
      // Also update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const filteredHistory = parsedHistory.filter((item: any) => item.id !== id);
        localStorage.setItem('researchHistory', JSON.stringify(filteredHistory));
      }
      
      return true;
    } catch (error) {
      console.error('Error deleting research:', error);
      
      // Update local state anyway
      setHistory(prev => prev.filter(item => item.id !== id));
      
      // Update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const filteredHistory = parsedHistory.filter((item: any) => item.id !== id);
        localStorage.setItem('researchHistory', JSON.stringify(filteredHistory));
      }
      
      return false;
    }
  };

  // Add chat message
  const addChatMessage = async (id: string, message: ChatMessage) => {
    try {
      const response = await fetch(`/api/reports/${id}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(message),
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      // Update local state
      setHistory(prev => 
        prev.map(item => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        })
      );
      
      // Also update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        });
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return true;
    } catch (error) {
      console.error('Error adding chat message:', error);
      
      // Update local state anyway
      setHistory(prev => 
        prev.map(item => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        })
      );
      
      // Update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        });
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return false;
    }
  };

  // Get chat messages
  const getChatMessages = (id: string) => {
    // First try to get from local state
    // Add defensive check to ensure history is an array before using find
    if (Array.isArray(history)) {
      const research = history.find(item => item.id === id);
      if (research && research.chatMessages) {
        return research.chatMessages;
      }
    } else {
      console.warn('History is not an array when getting chat messages');
    }
    
    // Fallback to localStorage
    const localHistory = localStorage.getItem('researchHistory');
    if (localHistory) {
      try {
        const parsedHistory = JSON.parse(localHistory);
        // Check if parsedHistory is an array
        if (Array.isArray(parsedHistory)) {
          const research = parsedHistory.find((item: any) => item.id === id);
          if (research && research.chatMessages) {
            return research.chatMessages;
          }
        } else {
          console.warn('Parsed history from localStorage is not an array');
        }
      } catch (error) {
        console.error('Error parsing history from localStorage:', error);
      }
    }
    
    return [];
  };

  // Clear all history from local storage and server
  const clearHistory = async () => {
    try {
      // Not implementing bulk delete on the server for now
      // This would require a new API endpoint
      
      // Just clear local state and storage
      setHistory([]);
      localStorage.removeItem('researchHistory');
      
      return true;
    } catch (error) {
      console.error('Error clearing history:', error);
      return false;
    }
  };

  return {
    history,
    loading,
    saveResearch,
    updateResearch,
    getResearchById,
    deleteResearch,
    addChatMessage,
    getChatMessages,
    clearHistory
  };
};
