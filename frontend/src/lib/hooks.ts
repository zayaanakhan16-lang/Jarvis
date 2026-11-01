/** Data-fetching and live-stream hooks. */

import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, activitySocketUrl, api } from './api'
import type { ActivityEvent } from './types'

export interface QueryState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Fetch data and expose its real loading and error state.
 *
 * ``error`` always carries the backend's own message, so a failure is reported
 * rather than hidden behind an empty result.
 */
export function useQuery<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  options: { pollMs?: number } = {},
): QueryState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false

    const run = async (showLoading: boolean) => {
      if (showLoading) setLoading(true)
      try {
        const result = await loaderRef.current()
        if (cancelled) return
        setData(result)
        setError(null)
      } catch (cause) {
        if (cancelled) return
        setError(
          cause instanceof ApiError
            ? cause.detail
            : cause instanceof Error
              ? cause.message
              : 'Unknown error',
        )
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void run(true)

    let timer: number | undefined
    if (options.pollMs) {
      timer = window.setInterval(() => void run(false), options.pollMs)
    }
    return () => {
      cancelled = true
      if (timer) window.clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, options.pollMs])

  return { data, loading, error, reload }
}

export interface ActivityStream {
  events: ActivityEvent[]
  connected: boolean
  error: string | null
  clear: () => void
}

/**
 * Subscribe to the backend's real activity stream.
 *
 * The socket only relays events the backend actually recorded; a heartbeat
 * keeps the connection alive and is never shown as activity.
 */
export function useActivityStream(projectId?: string, limit = 200): ActivityStream {
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const retryRef = useRef(0)

  // The stream only carries events that happen while the socket is open, so
  // seed from the REST log first. Without this the log looks empty on load
  // even though the backend has recorded real history.
  useEffect(() => {
    let cancelled = false
    api
      .activity({ project_id: projectId, limit })
      .then((history) => {
        if (cancelled) return
        // Newest first, matching the order the stream prepends in.
        setEvents([...history].reverse().slice(0, limit))
      })
      .catch(() => {
        // A failed backfill is not fatal: live events still arrive.
      })
    return () => {
      cancelled = true
    }
  }, [projectId, limit])

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let closed = false

    const connect = () => {
      try {
        socket = new WebSocket(activitySocketUrl(projectId))
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Could not open the stream.')
        return
      }

      socket.onopen = () => {
        setConnected(true)
        setError(null)
        retryRef.current = 0
      }

      socket.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data as string)
          if (payload.type === 'event' && payload.event) {
            const incoming = payload.event as ActivityEvent
            setEvents((previous) => {
              if (previous.some((existing) => existing.id === incoming.id)) return previous
              return [incoming, ...previous].slice(0, limit)
            })
          }
        } catch {
          // Ignore frames that are not valid JSON.
        }
      }

      socket.onerror = () => setError('The activity stream reported an error.')

      socket.onclose = () => {
        setConnected(false)
        if (closed) return
        retryRef.current += 1
        const delay = Math.min(1000 * 2 ** Math.min(retryRef.current, 5), 20000)
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      closed = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [projectId, limit])

  const clear = useCallback(() => setEvents([]), [])
  return { events, connected, error, clear }
}
