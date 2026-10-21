import axios, { AxiosInstance, AxiosError } from 'axios'

const API_BASE = '/api'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE,
      timeout: 60000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.client.interceptors.response.use(
      response => response,
      (error: AxiosError) => {
        if (error.response) {
          const data = error.response.data as { error?: string } | undefined
          return Promise.reject({
            status: error.response.status,
            message: data?.error || error.message,
            data: error.response.data,
          })
        }
        return Promise.reject({
          status: 0,
          message: error.message,
        })
      }
    )
  }

  async unfoldStepFile(
    file: File,
    options: { k_factor: number; kerf: number; bend_table?: object }
  ) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('k_factor', options.k_factor.toString())
    formData.append('kerf', options.kerf.toString())
    if (options.bend_table) {
      formData.append('bend_table', JSON.stringify(options.bend_table))
    }

    const response = await this.client.post<{
      success: boolean
      unfolded?: {
        profile_svg: string
        bend_lines: number[][][]
        bends: Array<{
          index: number
          angle_deg: number
          direction: string
          inside_radius: number
          bend_allowance: number
          k_factor: number
          bend_line_start: number[]
          bend_line_end: number[]
          flange_length_side_a: number
          flange_length_side_b: number
          nearest_cut_distance: number
          axis_point: number[]
          axis_direction: number[]
        }>
        thickness: number
        k_factor: number
        kerf: number
        blank_area: number
        volume: number
        material_conservation_ratio: number
        warnings: string[]
      }
      error_code?: string
      error_message?: string
      processing_time_ms: number
    }>('/unfold', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })

    return response.data
  }

  async healthCheck() {
    const response = await this.client.get<{ status: string; service: string; version: string }>('/unfold/health')
    return response.data
  }
}

export const api = new ApiClient()