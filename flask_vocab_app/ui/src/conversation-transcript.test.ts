import { describe, expect, it } from 'vitest';
import { russianTranscript } from './conversation-transcript';
import { captionRows, type Caption } from './live-connection';

describe('Russian conversation transcripts', () => {
  it.each([
    "How's things going? Hello, how's things going",
    "I'd like some coffee and some tea",
    "I'm going on holiday on Thursday. Do you want to come with me?",
    'I', ' H', 'Я хочу coffee', 'Я хочу c',
  ])('never displays English or incomplete mixed text: %s', text => {
    expect(russianTranscript(text)).toBeNull();
  });
  it.each(['Я хотеть чай без сахар.', '  Я… нет, ча́й. ', 'Чай, пожалуйста.', '180', 'Мне чёрный чай.'])('preserves Russian exactly: %s', text => {
    expect(russianTranscript(text)).toBe(text);
  });
  it('filters complete display groups without mutating the original deltas', () => {
    const fragments: Caption[] = [
      {type:'session.input_transcript.delta',delta:"I'd like ",start_ms:0,end_ms:100},
      {type:'session.input_transcript.delta',delta:'some coffee.',start_ms:100,end_ms:500},
      {type:'session.output_transcript.delta',delta:'Извините, я не понимаю.',start_ms:800,end_ms:1200},
      {type:'session.input_transcript.delta',delta:'Я хотеть чай без сахар.',start_ms:4000,end_ms:5000},
    ];
    const original=structuredClone(fragments);
    expect(captionRows(fragments).map(row=>row.text)).toEqual(['Извините, я не понимаю.','Я хотеть чай без сахар.']);
    expect(fragments).toEqual(original);
  });
  it('never constructs a Russian sentence by stripping an English fragment', () => {
    expect(captionRows([
      {type:'session.input_transcript.delta',delta:'Я хочу ',start_ms:0,end_ms:100},
      {type:'session.input_transcript.delta',delta:'coffee',start_ms:100,end_ms:200},
      {type:'session.input_transcript.delta',delta:' пожалуйста.',start_ms:200,end_ms:300},
    ])).toEqual([]);
  });
  it('keeps a quick Russian retry separate from English before the worker replied', () => {
    expect(captionRows([
      {type:'session.input_transcript.delta',delta:'Coffee please.',start_ms:0,end_ms:500},
      {type:'session.output_transcript.delta',delta:'Простите?',start_ms:600,end_ms:900},
      {type:'session.input_transcript.delta',delta:'Кофе, пожалуйста.',start_ms:1000,end_ms:1500},
    ]).map(row=>row.text)).toEqual(['Простите?','Кофе, пожалуйста.']);
  });
});
