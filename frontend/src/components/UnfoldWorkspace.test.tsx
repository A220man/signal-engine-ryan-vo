import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { UnfoldWorkspace } from './UnfoldWorkspace'
import { api } from '../api/client'

// Mock the API client
vi.mock('../api/client', () => ({
  api: {
    unfoldStepFile: vi.fn(),
    healthCheck: vi.fn(),
  },
}))

const mockUnfoldResponse = {
  success: true,
  unfolded: {
    profile_svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M 0 0 L 100 0 L 100 100 L 0 100 Z"/></svg>',
    bend_lines: [[[10, 10], [90, 10]], [[10, 90], [90, 90]]],
    bends: [
      {
        index: 0,
        angle_deg: 90,
        direction: 'up',
        inside_radius: 2.0,
        bend_allowance: 4.18,
        k_factor: 0.33,
        bend_line_start: [10, 10],
        bend_line_end: [90, 10],
        flange_length_side_a: 40,
        flange_length_side_b: 60,
        nearest_cut_distance: 15.0,
        axis_point: [50, 0, 2],
        axis_direction: [0, 1, 0],
      },
      {
        index: 1,
        angle_deg: 90,
        direction: 'down',
        inside_radius: 2.0,
        bend_allowance: 4.18,
        k_factor: 0.33,
        bend_line_start: [10, 90],
        bend_line_end: [90, 90],
        flange_length_side_a: 40,
        flange_length_side_b: 60,
        nearest_cut_distance: 15.0,
        axis_point: [50, 100, 2],
        axis_direction: [0, 1, 0],
      },
    ],
    thickness: 2.0,
    k_factor: 0.33,
    kerf: 0.0,
    blank_area: 8236,
    volume: 16472,
    material_conservation_ratio: 1.0,
    warnings: [],
  },
  processing_time_ms: 150,
}

describe('UnfoldWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.healthCheck).mockResolvedValue({ status: 'ok', service: 'signal-engine', version: '1.0.0' })
  })

  it('renders upload step initially', () => {
    render(<UnfoldWorkspace />)
    expect(screen.getByText('Upload STEP File')).toBeInTheDocument()
    expect(screen.getByText('Drag and drop a STEP file, or click to browse')).toBeInTheDocument()
  })

  it('shows error for non-STEP file', () => {
    render(<UnfoldWorkspace />)
    const input = screen.getByTestId('file-upload') as HTMLInputElement
    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    fireEvent.change(input, { target: { files: [file] } })
    expect(screen.getByText('Please select a STEP file (.step or .stp)')).toBeInTheDocument()
  })

  it('accepts STEP file and shows parameters', () => {
    render(<UnfoldWorkspace />)
    const input = screen.getByTestId('file-upload') as HTMLInputElement
    const file = new File(['content'], 'test.step', { type: 'application/step' })
    fireEvent.change(input, { target: { files: [file] } })
    expect(screen.getByText('Selected: test.step')).toBeInTheDocument()
    expect(screen.getByLabelText('K-Factor')).toBeInTheDocument()
    expect(screen.getByLabelText('Kerf Offset (mm)')).toBeInTheDocument()
    expect(screen.getByText('Generate Flat Pattern')).toBeInTheDocument()
  })

  it('calls API and shows result on success', async () => {
    vi.mocked(api.unfoldStepFile).mockResolvedValue(mockUnfoldResponse)

    render(<UnfoldWorkspace />)
    const input = screen.getByTestId('file-upload') as HTMLInputElement
    const file = new File(['content'], 'test.step', { type: 'application/step' })
    fireEvent.change(input, { target: { files: [file] } })

    fireEvent.click(screen.getByText('Generate Flat Pattern'))

    await waitFor(() => {
      expect(screen.getByText('Flat Pattern Result')).toBeInTheDocument()
    })

    expect(screen.getByText('Bend 1')).toBeInTheDocument()
    expect(screen.getByText('Bend 2')).toBeInTheDocument()
    expect(screen.getByText('Download DXF')).toBeInTheDocument()
  })

  it('shows error when API fails', async () => {
    vi.mocked(api.unfoldStepFile).mockResolvedValue({
      success: false,
      error_code: 'NOT_SHEET',
      error_message: 'No single thickness winner',
      processing_time_ms: 50,
    })

    render(<UnfoldWorkspace />)
    const input = screen.getByTestId('file-upload') as HTMLInputElement
    const file = new File(['content'], 'test.step', { type: 'application/step' })
    fireEvent.change(input, { target: { files: [file] } })

    fireEvent.click(screen.getByText('Generate Flat Pattern'))

    // Check that error state is set (may need a tick)
    await waitFor(() => {
      expect(screen.queryByText('Unfold failed: No single thickness winner') || screen.queryByText('No single thickness winner')).toBeTruthy()
    }, { timeout: 2000 })
  })

  it('shows loading state during API call', async () => {
    let resolvePromise: (value: unknown) => void
    const promise = new Promise(resolve => { resolvePromise = resolve })
    vi.mocked(api.unfoldStepFile).mockReturnValue(promise as any)

    render(<UnfoldWorkspace />)
    const input = screen.getByTestId('file-upload') as HTMLInputElement
    const file = new File(['content'], 'test.step', { type: 'application/step' })
    fireEvent.change(input, { target: { files: [file] } })

    // Wait for file selection to register
    await waitFor(() => {
      expect(screen.getByText('Selected: test.step')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Generate Flat Pattern'))

    // Loading state should appear immediately after click
    expect(screen.getByText('Processing...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Processing/ })).toBeDisabled()

    resolvePromise!(mockUnfoldResponse)
    await waitFor(() => {
      expect(screen.getByText('Flat Pattern Result')).toBeInTheDocument()
    }, { timeout: 1000 })
  })

  it('allows starting a new file from result view', async () => {
    vi.mocked(api.unfoldStepFile).mockResolvedValue(mockUnfoldResponse)

    render(<UnfoldWorkspace />)
    const input = screen.getByTestId('file-upload') as HTMLInputElement
    const file = new File(['content'], 'test.step', { type: 'application/step' })
    fireEvent.change(input, { target: { files: [file] } })

    fireEvent.click(screen.getByText('Generate Flat Pattern'))

    await waitFor(() => {
      expect(screen.getByText('Flat Pattern Result')).toBeInTheDocument()
    }, { timeout: 1000 })

    fireEvent.click(screen.getByLabelText('New file'))

    expect(screen.getByText('Upload STEP File')).toBeInTheDocument()
  })
})