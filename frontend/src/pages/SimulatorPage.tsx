import React, { useEffect, useState } from 'react';
import { CalendarClock, Cpu, Plus, Server, Zap } from 'lucide-react';
import { api } from '../api/client';
import type { AppSettings, Device, MockServiceNowChange, SchedulerStatus } from '../types';

export const SimulatorPage: React.FC = () => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [snowChanges, setSnowChanges] = useState<MockServiceNowChange[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);

  const [title, setTitle] = useState('Emergency WAN Failover & Core Route Update');
  const [engineerName, setEngineerName] = useState('Morgan Taylor');
  const [engineerEmail, setEngineerEmail] = useState('morgan.taylor@netops.local');
  const [offsetMinutes, setOffsetMinutes] = useState(61);
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<number[]>([]);
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const load = async () => {
    try {
      const [devs, snows, sched, cfg] = await Promise.all([
        api.listDevices(),
        api.listMockSnowChanges(),
        api.getSchedulerStatus(),
        api.getSettings(),
      ]);
      setDevices(devs);
      setSnowChanges(snows);
      setScheduler(sched);
      setSettings(cfg);
      if (selectedDeviceIds.length === 0 && devs.length > 0) {
        setSelectedDeviceIds(devs.slice(0, 2).map((d) => d.id));
      }
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const toggleDevice = (id: number) => {
    setSelectedDeviceIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleCreateSnowChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    if (selectedDeviceIds.length === 0) {
      setFeedback({ type: 'err', text: 'Select at least one network CI device.' });
      return;
    }
    try {
      const startIso = new Date(Date.now() + offsetMinutes * 60_000).toISOString();
      const created = await api.createMockSnowChange({
        title,
        description: 'Created from built-in ServiceNow Simulator for live T-1h scheduler demonstration.',
        scheduled_start: startIso,
        engineer_name: engineerName,
        engineer_email: engineerEmail,
        ci_device_ids: selectedDeviceIds,
      });
      setFeedback({
        type: 'ok',
        text: `Created simulated ServiceNow ticket ${created.chg_number} and synced it to Change Tracking.`,
      });
      await load();
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  const handleMoveToDueNow = async (rec: MockServiceNowChange) => {
    setFeedback(null);
    try {
      // Setting scheduled_start to +55 minutes puts T-1h five minutes in the past -> due immediately!
      await api.updateMockSnowChange(rec.id, {
        scheduled_start: new Date(Date.now() + 55 * 60_000).toISOString(),
        state: 'scheduled',
      });
      const res = await api.dispatchSchedulerNow();
      setFeedback({
        type: 'ok',
        text: `Rescheduled ${rec.chg_number} into T-1h window and dispatched ${res.dispatched_change_ids.length} pre-capture job(s).`,
      });
      await load();
    } catch (err) {
      setFeedback({ type: 'err', text: (err as Error).message });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">ServiceNow Simulator &amp; Managed Devices</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Create or reschedule simulated ServiceNow network changes to test T-1h automatic scheduling, and inspect multi-vendor device collectors and concurrency runtime.
        </p>
      </div>

      {feedback && (
        <div
          className={`px-4 py-3 rounded-lg text-sm border ${
            feedback.type === 'ok'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-red-50 text-red-800 border-red-200'
          }`}
        >
          {feedback.text}
        </div>
      )}

      {/* Runtime Concurrency & Scheduler Info */}
      {settings && scheduler && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div className="flex items-start gap-2.5">
            <Cpu className="w-4 h-4 text-indigo-600 mt-0.5" />
            <div>
              <div className="font-semibold text-slate-700 uppercase">Pipeline Concurrency</div>
              <div className="font-mono text-slate-900 mt-0.5">
                {settings.pipeline_executor_mode.toUpperCase()} ({settings.pipeline_max_workers} workers)
              </div>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <Server className="w-4 h-4 text-indigo-600 mt-0.5" />
            <div>
              <div className="font-semibold text-slate-700 uppercase">Device Polling Semaphore</div>
              <div className="font-mono text-slate-900 mt-0.5">
                Max {settings.max_concurrent_device_collections} concurrent devices
              </div>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <CalendarClock className="w-4 h-4 text-indigo-600 mt-0.5" />
            <div>
              <div className="font-semibold text-slate-700 uppercase">ServiceNow Window</div>
              <div className="font-mono text-slate-900 mt-0.5">
                Next {settings.servicenow_window_hours}h · T-{settings.pre_capture_lead_minutes}m lead
              </div>
            </div>
          </div>
          <div>
            <div className="font-semibold text-slate-700 uppercase">Scheduler Heartbeat</div>
            <div className="font-mono text-slate-900 mt-0.5">
              {scheduler.running ? 'RUNNING' : 'STOPPED'} · Pending: {scheduler.pending_pre_captures}
            </div>
          </div>
        </div>
      )}

      {/* Create Simulated ServiceNow Change */}
      <form
        onSubmit={handleCreateSnowChange}
        className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4"
      >
        <div className="font-semibold text-slate-900">
          Create Simulated ServiceNow Network Change
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
              Change Title
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
              Starts In (Minutes from Now)
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={1440}
                value={offsetMinutes}
                onChange={(e) => setOffsetMinutes(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono"
              />
              <button
                type="button"
                onClick={() => setOffsetMinutes(61)}
                className="px-2.5 py-1 text-xs rounded-lg bg-slate-100 hover:bg-slate-200 whitespace-nowrap"
              >
                61m (T-1h in 1m)
              </button>
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
              Engineer Name
            </label>
            <input
              type="text"
              required
              value={engineerName}
              onChange={(e) => setEngineerName(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
              Engineer Email (Mailpit Target)
            </label>
            <input
              type="email"
              required
              value={engineerEmail}
              onChange={(e) => setEngineerEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
              Associated Network CIs
            </label>
            <div className="flex flex-wrap gap-2 pt-1">
              {devices.map((dev) => (
                <label
                  key={dev.id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-200 bg-slate-50 text-xs font-mono cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedDeviceIds.includes(dev.id)}
                    onChange={() => toggleDevice(dev.id)}
                  />
                  {dev.hostname}
                </label>
              ))}
            </div>
          </div>
        </div>
        <button
          type="submit"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white"
        >
          <Plus className="w-4 h-4" />
          Schedule Change in Mock ServiceNow
        </button>
      </form>

      {/* Existing Simulated Changes */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-200 font-semibold text-slate-800">
          Simulated ServiceNow Tickets ({snowChanges.length})
        </div>
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 text-left font-semibold">CHG Number</th>
              <th className="px-4 py-3 text-left font-semibold">Title &amp; Assignee</th>
              <th className="px-4 py-3 text-left font-semibold">Scheduled Start</th>
              <th className="px-4 py-3 text-left font-semibold">State</th>
              <th className="px-5 py-3 text-right font-semibold">Demo Shortcut</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {snowChanges.map((rec) => (
              <tr key={rec.id}>
                <td className="px-5 py-3 font-mono font-bold text-slate-900">{rec.chg_number}</td>
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-800">{rec.title}</div>
                  <div className="text-xs text-slate-500">
                    {rec.engineer_name} ({rec.engineer_email})
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-slate-700">
                  {new Date(rec.scheduled_start).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-xs font-mono uppercase">{rec.state}</td>
                <td className="px-5 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => handleMoveToDueNow(rec)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-100 hover:bg-amber-200 text-amber-900 border border-amber-300"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    Fast-Forward to T-1h
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Managed Multi-Vendor Device Inventory */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-200 font-semibold text-slate-800">
          Managed Network Devices ({devices.length})
        </div>
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 text-left font-semibold">Hostname</th>
              <th className="px-4 py-3 text-left font-semibold">Management IP</th>
              <th className="px-4 py-3 text-left font-semibold">Vendor Adapter</th>
              <th className="px-4 py-3 text-left font-semibold">Mode</th>
              <th className="px-4 py-3 text-left font-semibold">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {devices.map((dev) => (
              <tr key={dev.id}>
                <td className="px-5 py-3 font-mono font-bold text-slate-900">{dev.hostname}</td>
                <td className="px-4 py-3 font-mono text-slate-700">{dev.ip_address}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-mono">
                    {dev.device_type}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs font-mono uppercase">{dev.connection_mode}</td>
                <td className="px-4 py-3 text-xs text-slate-600">{dev.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
