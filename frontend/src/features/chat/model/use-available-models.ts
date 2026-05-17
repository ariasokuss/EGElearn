"use client"

import { useState, useEffect } from "react"

import type { ModelOption } from "@/entities/chat"
import { getAvailableModelsApiV1ChatAvailableModelsGet } from "@/shared/api/generated/api"

type AvailableModelsState = {
  models: ModelOption[]
  reasoningLevels: string[]
  isLoading: boolean
  error: string | null
}

export function useAvailableModels() {
  const [state, setState] = useState<AvailableModelsState>({
    models: [],
    reasoningLevels: [],
    isLoading: true,
    error: null,
  })

  useEffect(() => {
    let cancelled = false

    async function fetchModels() {
      setState((prev) => ({ ...prev, isLoading: true, error: null }))

      try {
        const res = await getAvailableModelsApiV1ChatAvailableModelsGet()

        if (res.status < 200 || res.status >= 300) {
          throw new Error(`Failed to load models (${res.status})`)
        }

        const { models, reasoningLevels } = parseAvailableModelsResponse(res.data)

        if (!cancelled) {
          setState({ models, reasoningLevels, isLoading: false, error: null })
        }
      } catch (err) {
        if (!cancelled) {
          setState((prev) => ({
            ...prev,
            isLoading: false,
            error: err instanceof Error ? err.message : "Failed to load models",
          }))
        }
      }
    }

    fetchModels()
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

/**
 * Parse the API response into model and reasoning option lists.
 * Handles array, wrapped array, and dict shapes defensively.
 */
function parseAvailableModelsResponse(data: unknown): {
  models: ModelOption[]
  reasoningLevels: string[]
} {
  if (!data) return { models: [], reasoningLevels: [] }

  // If response is an array of model objects
  if (Array.isArray(data)) {
    return {
      models: data
        .map((item) => parseModelItem(item))
        .filter((m): m is ModelOption => m !== null),
      reasoningLevels: [],
    }
  }

  if (typeof data === "object") {
    const obj = data as Record<string, unknown>
    const reasoningLevels = normalizeStringArray(
      obj.reasoning_levels ?? obj.reasoningLevels ?? obj.reasoning,
    )

    if ("models" in obj || "reasoning_levels" in obj || "reasoningLevels" in obj) {
      return {
        models: Array.isArray(obj.models)
          ? obj.models
            .map((item) => parseModelItem(item))
            .filter((m): m is ModelOption => m !== null)
          : [],
        reasoningLevels,
      }
    }

    // If response has a `models`, `data`, or `items` wrapper with an array
    const inner = obj.models ?? obj.data ?? obj.items
    if (Array.isArray(inner)) {
      return {
        models: inner
          .map((item) => parseModelItem(item))
          .filter((m): m is ModelOption => m !== null),
        reasoningLevels,
      }
    }

    // Dict format: { "model-id": { name: "...", ... }, ... }
    // or simple dict: { "model-id": "Display Name", ... }
    const entries = Object.entries(obj)
    if (entries.length > 0) {
      return {
        models: entries
          .map(([key, value]) => parseDictEntry(key, value))
          .filter((m): m is ModelOption => m !== null),
        reasoningLevels,
      }
    }
  }

  return { models: [], reasoningLevels: [] }
}

function parseModelItem(item: unknown): ModelOption | null {
  // Plain string: "ChatGPT 5.4" → { id: "ChatGPT 5.4", name: "ChatGPT 5.4" }
  if (typeof item === "string" && item.length > 0) {
    return { id: item, name: item, provider: "" }
  }

  if (!item || typeof item !== "object") return null
  const obj = item as Record<string, unknown>

  const id = (obj.id ?? obj.model_id ?? obj.key) as string | undefined
  const name = (obj.name ?? obj.display_name ?? obj.label ?? id) as string | undefined
  const provider = (obj.provider ?? obj.vendor ?? "") as string

  if (!id || !name) return null

  return { id, name, provider }
}

function parseDictEntry(key: string, value: unknown): ModelOption | null {
  // { "model-id": "Display Name" }
  if (typeof value === "string") {
    return { id: key, name: value, provider: "" }
  }

  // { "model-id": { name: "...", provider: "..." } }
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>
    const name = (obj.name ?? obj.display_name ?? obj.label ?? key) as string
    const provider = (obj.provider ?? obj.vendor ?? "") as string
    return { id: obj.id ? String(obj.id) : key, name, provider }
  }

  return null
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => item.length > 0)
}
