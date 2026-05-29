import React from 'react';

type Props = { children: React.ReactNode; label?: string };
type State = { error: Error | null };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('[Pulse]', this.props.label ?? 'panel', 'crashed:', error.message, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="panel p-4 border-bear/40">
          <div className="text-bear text-[11px] font-mono uppercase tracking-widest mb-2">⚠ {this.props.label ?? 'Panel'} failed</div>
          <div className="text-[10px] font-mono text-text-tertiary mb-2">{this.state.error.message}</div>
          <button
            onClick={() => this.setState({ error: null })}
            className="text-[10px] font-mono px-2 py-1 rounded border border-border text-text-secondary hover:text-gold hover:border-gold"
          >
            retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
