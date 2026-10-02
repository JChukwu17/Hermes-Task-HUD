/**
 * task-hud — Hermes desktop plugin
 * Adds a palette command ("Show Task HUD") and a status-bar chip so the
 * floating task-progress widget can be opened from within Hermes desktop.
 *
 * The widget itself is served by hermes_hud.py on http://127.0.0.1:47614.
 * If pywebview isn't installed the plugin opens it in the default browser.
 */
import { haptic } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

const ID = 'task-hud'
const WIDGET_URL = 'http://127.0.0.1:47614/hermes-task-widget.html'

function TaskChip() {
  return jsx('button', {
    className: 'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem]',
    style: { color: 'var(--ui-text-tertiary)' },
    onClick: () => {
      haptic('tap')
      ctx.os.openExternal(WIDGET_URL)
    },
    children: [
      jsx('span', { style: { fontSize: '0.9em' }, children: '●' }),
      ' Task HUD'
    ]
  })
}

export default {
  id: ID,
  name: 'Task HUD',
  defaultEnabled: false,
  register(ctx) {
    // Status-bar chip (right side)
    ctx.register({
      id: 'chip',
      area: 'statusBar.right',
      order: 120,
      render: () => jsx(TaskChip, {})
    })

    // Palette command
    ctx.register({
      id: 'open-hud',
      area: 'palette',
      data: {
        id: 'task-hud.open',
        label: 'Show Task HUD',
        keywords: ['hud', 'task', 'progress', 'widget'],
        run: () => {
          haptic('tap')
          ctx.os.openExternal(WIDGET_URL)
        }
      }
    })
  }
}
