"""The manual preparation command must bound paid calls and preserve successes."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch


SPEC=importlib.util.spec_from_file_location(
    'prepare_delivery_audio_command',
    Path(__file__).resolve().parents[2]/'scripts/prepare_delivery_audio.py',
)
command=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)


class DeliveryAudioCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.audio=self.root/'flask_vocab_app/static/audio/deliveries'
        self.manifest=self.audio/'manifest.json'
        self.config={'ELEVENLABS_VOICE_IDS':['test-voice'],
                     'ELEVENLABS_API_KEY':'test-key','ELEVENLABS_MODEL':'test-model'}
        self.clips=[{'id':f'clip-{i}','text':f'Указание {i}.','speaker':'nina'} for i in range(4)]
        self.provider=Mock()
        self.provider.speak.return_value=b'test-audio'
        self.stack=contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(command,'ROOT',self.root))
        self.stack.enter_context(patch.object(command,'app_config',return_value=self.config.copy()))
        self.stack.enter_context(patch.object(command,'SPEAKERS',{'nina':{}}))
        self.stack.enter_context(patch.object(command,'all_audio',return_value=self.clips[:1]))
        self.constructor=self.stack.enter_context(patch.object(command,'SpeechProvider',return_value=self.provider))
        self.output=self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def generated(self, clips):
        module=types.ModuleType('services.route_dispatch')
        module.all_audio=lambda:clips
        self.stack.enter_context(patch.dict('sys.modules',{'services.route_dispatch':module}))

    def test_generated_dry_run_counts_deduplicated_clips_without_writes_or_calls(self):
        self.generated(self.clips)
        command.main(['--generated','--dry-run','--workers','3'])
        self.assertIn('4 new recordings',self.output.getvalue())
        self.constructor.assert_not_called()
        self.assertFalse(self.audio.exists())

    def test_limit_exceeded_never_constructs_provider_or_writes_manifest(self):
        self.generated(self.clips)
        with self.assertRaisesRegex(SystemExit,'limit exceeded'):
            command.main(['--generated','--max-new','3','--workers','3'])
        self.constructor.assert_not_called()
        self.assertFalse(self.audio.exists())

    def test_assignments_saved_before_calls_and_completed_clips_survive_failure(self):
        self.generated(self.clips)
        def speak(text, voice):
            saved=json.loads(self.manifest.read_text())
            self.assertEqual(saved['speakers']['nina'],voice)
            if text==self.clips[1]['text']:
                raise RuntimeError('Private provider error must not be printed')
            return b'finished-audio'
        self.provider.speak.side_effect=speak
        with self.assertRaisesRegex(SystemExit,'RuntimeError') as error:
            command.main(['--generated'])
        self.assertNotIn('Private provider error',str(error.exception))
        self.assertEqual(self.provider.speak.call_count,2)
        saved=json.loads(self.manifest.read_text())
        self.assertEqual(set(saved['clips']),{'clip-0'})
        self.assertEqual((self.audio/'clip-0.mp3').read_bytes(),b'finished-audio')
        self.assertFalse((self.audio/'clip-1.mp3').exists())
        self.assertEqual({path.name for path in self.audio.iterdir()},{'manifest.json','clip-0.mp3'})

    def test_workers_prepare_in_parallel_but_only_main_thread_saves(self):
        self.generated(self.clips[:3])
        barrier=threading.Barrier(3)
        worker_ids=set()
        def speak(text, voice):
            worker_ids.add(threading.get_ident())
            barrier.wait(timeout=3)
            return text.encode()
        self.provider.speak.side_effect=speak
        main_thread=threading.get_ident()
        write=command._write_atomic
        writes=[]
        def save(path,data):
            writes.append(threading.get_ident())
            return write(path,data)
        with patch.object(command,'_write_atomic',side_effect=save):
            command.main(['--generated','--workers','3'])
        self.assertEqual(len(worker_ids),3)
        self.assertNotIn(main_thread,worker_ids)
        self.assertEqual(set(writes),{main_thread})
        self.assertEqual(set(json.loads(self.manifest.read_text())['clips']),{'clip-0','clip-1','clip-2'})

    def test_failure_stops_new_requests_and_saves_other_in_flight_recording(self):
        self.generated(self.clips)
        barrier=threading.Barrier(2)
        failure_seen=threading.Event()
        def speak(text, voice):
            barrier.wait(timeout=3)
            if text==self.clips[0]['text']:
                raise RuntimeError('Failed request')
            self.assertTrue(failure_seen.wait(timeout=3))
            return b'other-call-finished'
        self.provider.speak.side_effect=speak
        real_wait=command.wait
        def observe_failure(*args,**kwargs):
            completed,pending=real_wait(*args,**kwargs)
            if any(future.exception() for future in completed):
                failure_seen.set()
            return completed,pending
        with patch.object(command,'wait',side_effect=observe_failure),self.assertRaises(SystemExit):
            command.main(['--generated','--workers','2'])
        self.assertEqual(self.provider.speak.call_count,2)
        self.assertEqual(set(json.loads(self.manifest.read_text())['clips']),{'clip-1'})
        self.assertEqual((self.audio/'clip-1.mp3').read_bytes(),b'other-call-finished')

    def test_rerun_reuses_recordings_and_preserves_voice_assignment(self):
        self.audio.mkdir(parents=True)
        (self.audio/'clip-0.mp3').write_bytes(b'original-audio')
        self.manifest.write_text(json.dumps({'provider':'elevenlabs','model':'test-model',
            'speakers':{'nina':'saved-voice'},'clips':{'clip-0':{'bytes':14}}}))
        self.generated(self.clips[:2])
        command.main(['--generated'])
        self.provider.speak.assert_called_once_with(self.clips[1]['text'],'saved-voice')
        self.assertEqual((self.audio/'clip-0.mp3').read_bytes(),b'original-audio')
        self.assertEqual(json.loads(self.manifest.read_text())['speakers']['nina'],'saved-voice')

    def test_worker_limit_rejects_unbounded_requests(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            command.main(['--workers','4'])
        self.constructor.assert_not_called()


if __name__=='__main__':
    unittest.main()
