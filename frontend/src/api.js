const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL

export const API_BASE_URL = (
  configuredBaseUrl || 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

function queryString(parameters) {
  const entries = Object.entries(parameters).filter(
    ([, value]) => value !== undefined && value !== null && value !== '',
  )
  return new URLSearchParams(entries).toString()
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new ApiError(
      `Could not connect to the API at ${API_BASE_URL}. Check the backend and VITE_API_BASE_URL.`,
      0,
    )
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join('; ')
      : detail || `The API returned HTTP ${response.status}.`
    throw new ApiError(message, response.status)
  }
  return body
}

export const api = {
  overview: () => request('/api/v1/dashboard/overview'),
  generationStatus: () => request('/api/v1/generation/status'),
  generationConfigurations: () => request('/api/v1/generation/configurations'),
  startGeneration: (configuration) =>
    request('/api/v1/generation', {
      method: 'POST',
      body: JSON.stringify(configuration),
    }),
  generationJob: (jobId) =>
    request(`/api/v1/generation/jobs/${encodeURIComponent(jobId)}`),
  products: (parameters) =>
    request(`/api/v1/catalog/products?${queryString(parameters)}`),
  categories: () => request('/api/v1/catalog/categories'),
  customers: (search) =>
    request(`/api/v1/customers?${new URLSearchParams({ search, limit: '25' })}`),
  recommend: (customerId, configuration) =>
    request(
      `/api/v1/recommendations/customers/${encodeURIComponent(customerId)}`,
      { method: 'POST', body: JSON.stringify(configuration) },
    ),
  validationSummary: () => request('/api/v1/validation/summary'),
  validationIssues: (parameters) =>
    request(`/api/v1/validation/issues?${queryString(parameters)}`),
  startValidation: (configuration = {}) =>
    request('/api/v1/validation', {
      method: 'POST',
      body: JSON.stringify(configuration),
    }),
  validationJob: (jobId) =>
    request(`/api/v1/validation/jobs/${encodeURIComponent(jobId)}`),
  validationStatus: () => request('/api/v1/validation/status'),
  evaluations: () =>
    request('/api/v1/recommendations/evaluations?limit=100'),
  runEvaluation: (kValues = [5, 10]) =>
    request('/api/v1/recommendations/evaluations', {
      method: 'POST',
      body: JSON.stringify({ k_values: kValues }),
    }),
  strategies: () => request('/api/v1/recommendations/strategies'),
}
