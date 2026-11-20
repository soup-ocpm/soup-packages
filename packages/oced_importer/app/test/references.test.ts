import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Block, ConfigContext, FormValues, TabularConfiguration } from '@soup/sdk';

import '../src/index';
import { Workflow, tableState } from '../src/workflow';

const source = {
  filename: 'events.csv', size: 100,
  columns: ['id', 'eventName', 'eventDatetime', 'playerId'],
  rows: [['e1', 'pass', '2020-01-01T00:00:00', 'p1,p2']],
  attr_types: { id: 'String', eventName: 'String', eventDatetime: 'Datetime', playerId: 'String' },
  file: { filename: 'events.csv', base64: '' }
};
const warning: Block = {
  type: 'table', title: 'Missing object references',
  data: { columns: ['Column', 'Missing IDs', 'Sample values'], rows: [['playerId', 1, 'p2']] }
};

afterEach(() => document.body.replaceChildren());

describe('Missing OCED object references', () => {
  it('defaults to strict validation and transmits the explicit selected policy', () => {
    const workflow = new Workflow(); workflow.add(tableState(source)); workflow.selectObject('playerId', true);
    expect(workflow.options()['missing_reference_strategy']).toBe('strict');
    for (const strategy of ['discard', 'placeholders']) {
      workflow.missingReferenceStrategy = strategy;
      expect(workflow.options()['missing_reference_strategy']).toBe(strategy);
    }
  });

  it.each(['discard', 'placeholders'])('blocks import until %s is explicitly selected and explains both options', async (strategy) => {
    let tabular!: TabularConfiguration;
    const emitted: FormValues[] = [];
    const preview = vi.fn(async () => [warning]);
    const config = document.createElement('soup-oced-importer-config') as HTMLElement & { context: ConfigContext };
    config.context = {
      importer: 'oced_importer.csv', fields: [{ name: 'source', default: source }], columns: source.columns, value: {},
      emit: (options: FormValues) => emitted.push(options), preview,
      tabular: (value: TabularConfiguration) => { tabular = value; }
    } as ConfigContext;
    document.body.append(config);
    tabular.onChange({ table: 'events.csv', column: 'playerId', kind: 'role', role: 'object', value: true });
    await vi.waitFor(() => expect(config.shadowRoot?.textContent).toContain('playerId: 1 distinct missing IDs. Samples: p2'));
    expect(emitted.at(-1)?.['config_error']).toContain('Strict validation');
    expect(config.shadowRoot?.textContent).toContain('keeps every event');
    expect(config.shadowRoot?.textContent).toContain('NULL attributes');
    const select = config.shadowRoot!.querySelector<HTMLSelectElement>('select[aria-label="Missing reference strategy"]')!;
    select.value = strategy; select.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(emitted.at(-1)?.['config_error']).toBeUndefined());
    expect(emitted.at(-1)?.['missing_reference_strategy']).toBe(strategy);
    expect(preview).toHaveBeenLastCalledWith(expect.objectContaining({ missing_reference_strategy: strategy }));
    // A failed policy preview (for example a cross-type placeholder ID collision)
    // must leave the strategy selector available so the user can recover.
    preview.mockRejectedValueOnce(new Error('Object ID collision'));
    const retry = config.shadowRoot!.querySelector<HTMLSelectElement>('select[aria-label="Missing reference strategy"]')!;
    retry.value = strategy; retry.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(emitted.at(-1)?.['config_error']).toContain('Object ID collision'));
    const recovery = config.shadowRoot!.querySelector<HTMLSelectElement>('select[aria-label="Missing reference strategy"]');
    expect(recovery).not.toBeNull();
    recovery!.value = 'strict'; recovery!.dispatchEvent(new Event('change'));
    await vi.waitFor(() => expect(emitted.at(-1)?.['config_error']).toContain('Strict validation'));
  });
});
