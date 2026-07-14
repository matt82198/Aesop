/**
 * MessagesTail — Role-colored recent main-thread messages with auto-follow toggle.
 * Scrolls to bottom when new messages arrive (if follow enabled).
 * User scroll up pauses auto-follow; toggle re-enables it.
 */

import { useEffect, useRef, useState } from 'react';
import { formatTimestamp } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import type { Message } from '../lib/types';
import styles from './MessagesTail.module.css';

const FOLLOW_THRESHOLD = 50; // pixels from bottom
const MAX_MESSAGES = 12; // Display last ~12 messages

interface Props {
  messages: Message[];
}

export default function MessagesTail({ messages }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isFollowing, setIsFollowing] = useState(true);

  // Detect if user scrolled up manually
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    if (distanceFromBottom > FOLLOW_THRESHOLD) {
      setIsFollowing(false);
    }
  };

  // Auto-scroll to bottom when new messages arrive (if following)
  useEffect(() => {
    if (!isFollowing || !containerRef.current) return;

    // Wait for DOM to update
    setTimeout(() => {
      const lastMessage = containerRef.current?.lastElementChild as HTMLElement;
      if (lastMessage?.scrollIntoView) {
        lastMessage.scrollIntoView({ behavior: 'smooth' });
      } else if (containerRef.current) {
        // Fallback for test environment
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    }, 0);
  }, [messages, isFollowing]);

  const displayMessages = messages.slice(-MAX_MESSAGES);

  return (
    <div data-testid={TESTIDS.messagesTail} className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>Main-Thread Messages</h3>
        <button
          type="button"
          data-testid={TESTIDS.messagesFollowToggle}
          aria-pressed={isFollowing}
          onClick={() => setIsFollowing(!isFollowing)}
          className={styles.toggleButton}
          title={isFollowing ? 'Stop auto-following' : 'Resume auto-following'}
        >
          {isFollowing ? '📌 Following' : '📌 Paused'}
        </button>
      </div>

      <div ref={containerRef} className={styles.messagesBox} onScroll={handleScroll}>
        {displayMessages.length === 0 ? (
          <div className={styles.emptyState}>(no messages)</div>
        ) : (
          displayMessages.map((msg, idx) => (
            <div
              key={idx}
              data-testid={`message-${idx}`}
              className={`${styles.message} ${styles[`role-${msg.role}`]}`}
            >
              <span className={styles.role}>{msg.role}</span>
              <span className={styles.timestamp}>{formatTimestamp(msg.timestamp)}</span>
              <div className={styles.text}>{msg.text}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
