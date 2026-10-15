import React from 'react';
import Modal from './Settings/Modal';
import { ChatBoxSettings } from '@/types/data';

interface FooterProps {
  chatBoxSettings: ChatBoxSettings;
  setChatBoxSettings: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
}

const Footer: React.FC<FooterProps> = ({ chatBoxSettings, setChatBoxSettings }) => {
  // Add domain filtering from URL parameters
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    const urlDomains = urlParams.get("domains");
    if (urlDomains) {
      // Split domains by comma if multiple domains are provided
      const domainArray = urlDomains.split(',').map(domain => ({
        value: domain.trim()
      }));
      localStorage.setItem('domainFilters', JSON.stringify(domainArray));
    }
  }

  return (
    <>
      <div className="container flex flex-col sm:flex-row min-h-[60px] sm:min-h-[72px] mt-2 items-center justify-center sm:justify-between border-t border-gray-700/30 px-4 pb-3 pt-4 sm:py-5 lg:px-0 bg-transparent backdrop-blur-sm gap-3 sm:gap-0">
        <Modal setChatBoxSettings={setChatBoxSettings} chatBoxSettings={chatBoxSettings} />
        <div className="text-xs sm:text-sm text-gray-100 text-center sm:text-left order-2 sm:order-1">
            Traceable Deep Researcher · Piao666
        </div>
        <div className="flex items-center gap-4 order-1 sm:order-2 mb-2 sm:mb-0">
          <a className="text-teal-300 hover:text-teal-200" href="https://github.com/piao666/Traceable-Deep-Researcher" target="_blank" rel="noopener noreferrer">GitHub</a>
          <a className="text-teal-300 hover:text-teal-200" href="mailto:dahaipiao9@gmail.com">Contact Piao666</a>
        </div>
      </div>
    </>
  );
};

export default Footer;
