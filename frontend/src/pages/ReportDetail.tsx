import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ArrowLeft, Play, Calendar } from 'lucide-react'
import { getReport, runReport } from '@/api/reports'
import { ResultChart } from '@/components/Chat/ResultChart'
import { DataTable } from '@/components/Chat/DataTable'
import { SqlBlock } from '@/components/Chat/SqlBlock'
import { InterpretationChips } from '@/components/Chat/InterpretationChips'
import { QueryData, ChartConfig } from '@/types'
import { useState } from 'react'
import { ScheduleModal } from '@/components/Schedule/ScheduleModal'

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [runData, setRunData] = useState<{ data: QueryData; chart: ChartConfig } | null>(null)
  const [showSchedule, setShowSchedule] = useState(false)

  const { data: report, isLoading } = useQuery({
    queryKey: ['report', id],
    queryFn: () => getReport(id!),
    enabled: !!id,
  })

  const runMutation = useMutation({
    mutationFn: () => runReport(id!),
    onSuccess: (result) => {
      if (result.data && result.chart) {
        setRunData({ data: result.data as QueryData, chart: result.chart as ChartConfig })
      }
    },
  })

  if (isLoading) {
    return <div className="flex-1 flex items-center justify-center text-text-muted text-sm">Загрузка...</div>
  }

  if (!report) {
    return <div className="flex-1 flex items-center justify-center text-error text-sm">Отчёт не найден</div>
  }

  const displayData = runData
  const displayChart = runData?.chart || report.chart_config

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 px-6 py-3.5 border-b border-border-default bg-bg-surface shrink-0">
        <button onClick={() => navigate('/reports')} className="text-text-muted hover:text-text-primary">
          <ArrowLeft size={16} />
        </button>
        <h1 className="font-semibold text-text-primary flex-1 truncate">{report.name}</h1>
        <div className="flex gap-2">
          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-bg-elevated border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover rounded-md transition-colors"
          >
            <Play size={12} />
            {runMutation.isPending ? 'Запуск...' : 'Обновить'}
          </button>
          <button
            onClick={() => setShowSchedule(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent-primary text-accent-text rounded-md hover:bg-accent-hover transition-colors"
          >
            <Calendar size={12} />
            Расписание
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4 max-w-3xl">
        {report.description && (
          <p className="text-sm text-text-secondary">{report.description}</p>
        )}

        {report.interpretation && (
          <InterpretationChips interpretation={report.interpretation} />
        )}

        {report.sql && <SqlBlock sql={report.sql} />}

        {displayData && displayChart && displayChart.type !== 'table' && (
          <div className="bg-bg-surface border border-border-default rounded-lg p-4">
            <ResultChart data={displayData.data} chart={displayChart} />
          </div>
        )}

        {displayData && (
          <DataTable data={displayData.data} defaultOpen />
        )}

        {!displayData && !runMutation.isPending && (
          <div className="text-center py-12 text-text-muted">
            <p className="text-sm">Нажмите «Обновить» для получения актуальных данных</p>
          </div>
        )}
      </div>

      {showSchedule && (
        <ScheduleModal report={report} onClose={() => setShowSchedule(false)} />
      )}
    </div>
  )
}
