# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
WebSocket consumer for the agentic chat panel.

Protocol (JSON messages over WebSocket):

  Client → Server:
    {"type": "chat.message", "conversation_id": int, "text": str}
    {"type": "tool.approve", "message_id": int}
    {"type": "tool.reject",  "message_id": int}

  Server → Client:
    {"type": "chat.token",       "content": str}
    {"type": "chat.tool_call",   "message_id": int, "name": str, "args": dict, "description": str}
    {"type": "chat.tool_result", "message_id": int, "name": str, "result": str}
    {"type": "chat.done",        "input_tokens": int, "output_tokens": int}
    {"type": "chat.error",       "message": str}
    {"type": "chat.summary",     "summary": str}
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser, User

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Handles real-time AI chat for the grading assistant."""

    user: Optional[User]
    submission_id: int

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self):
        self.submission_id = int(self.scope["url_route"]["kwargs"]["submission_id"])

        # Authenticate via token query param
        query = parse_qs((self.scope.get("query_string") or b"").decode())
        token_param = query.get("token", [None])[0]
        self.user = await self._authenticate(token_param)

        if not self.user or isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return

        # Authorize: must be staff of the submission
        has_access = await self._check_permission()
        if not has_access:
            await self.close(code=4003)
            return

        await self.accept()

    async def disconnect(self, code):
        pass

    # ------------------------------------------------------------------
    # Incoming messages
    # ------------------------------------------------------------------

    async def receive_json(self, content: dict, **kwargs):
        msg_type = content.get("type")
        try:
            if msg_type == "chat.message":
                await self._handle_chat_message(content)
            elif msg_type == "tool.approve":
                await self._handle_tool_approve(content)
            elif msg_type == "tool.reject":
                await self._handle_tool_reject(content)
            else:
                await self.send_json({"type": "chat.error", "message": f"Unknown message type: {msg_type}"})
        except Exception as e:
            logger.error(f"Chat consumer error: {e}", exc_info=True)
            await self.send_json({"type": "chat.error", "message": "An internal error occurred."})

    # ------------------------------------------------------------------
    # Chat message handling
    # ------------------------------------------------------------------

    async def _handle_chat_message(self, content: dict):
        from asgiref.sync import sync_to_async
        from core.models import ChatConversation, ChatMessage, Submission
        from core.services.ai_service import AIService
        from core.services.chat_tools import ALL_TOOLS, SERVER_SIDE_TOOLS, CLIENT_SIDE_TOOLS, execute_server_tool

        conversation_id = content.get("conversation_id")
        user_text = (content.get("text") or "").strip()
        if not user_text:
            await self.send_json({"type": "chat.error", "message": "Message text is required."})
            return

        # Parse optional editor context attached to the message
        context = content.get("context")
        context_prefix = ""
        if context and isinstance(context, dict):
            file_name = str(context.get("file_name", ""))[:200]
            start_line = context.get("start_line")
            end_line = context.get("end_line")
            selected_text = str(context.get("selected_text", ""))[:2500]

            if file_name:
                if selected_text:
                    line_ref = f"line {start_line}" if start_line == end_line else f"lines {start_line}-{end_line}"
                    context_prefix = (
                        f"[The grader is referring to {file_name} {line_ref}. "
                        f"Selected code:\n```\n{selected_text}\n```\n]\n\n"
                    )
                else:
                    context_prefix = f"[The grader is referring to {file_name}]\n\n"

        # Load conversation and verify ownership
        try:
            conversation = await sync_to_async(
                lambda: ChatConversation.objects.select_related(
                    'submission', 'assignment', 'assignment__course'
                ).get(pk=conversation_id, user=self.user, submission_id=self.submission_id)
            )()
        except ChatConversation.DoesNotExist:
            await self.send_json({"type": "chat.error", "message": "Conversation not found."})
            return

        # Save user message
        user_msg = await sync_to_async(ChatMessage.objects.create)(
            conversation=conversation, role='user', content=user_text
        )

        # Auto-generate title from first message
        if not conversation.title:
            conversation.title = user_text[:100]
            await sync_to_async(conversation.save)()

        # Build message history
        db_messages = await sync_to_async(
            lambda: list(conversation.messages.order_by('created').values('role', 'content', 'tool_name', 'tool_args', 'tool_status'))
        )()

        # Build LLM messages
        system_prompt = await self._build_system_prompt(conversation)
        llm_messages = [{"role": "system", "content": system_prompt}]

        # If there's a summary, insert it first
        if conversation.summary:
            llm_messages.append({"role": "assistant", "content": f"[Previous conversation summary]: {conversation.summary}"})

        # Check if we need to summarize (auto-summarization)
        ai_service = await self._get_ai_service(conversation)
        if len(db_messages) > AIService.SUMMARIZE_THRESHOLD and ai_service:
            # Summarize older messages
            old_messages = db_messages[:-AIService.SUMMARIZE_THRESHOLD]
            summary_input = [
                {"role": m["role"] if m["role"] in ("user", "assistant") else "assistant", "content": m["content"]}
                for m in old_messages if m["content"]
            ]
            summary = await ai_service.summarize_conversation(summary_input)
            if summary:
                conversation.summary = summary
                await sync_to_async(conversation.save)()
                await self.send_json({"type": "chat.summary", "summary": summary})
                # Save summary message
                await sync_to_async(ChatMessage.objects.create)(
                    conversation=conversation, role='summary', content=summary
                )

        # Convert DB messages to LLM format (only recent ones if summarized)
        recent_messages = db_messages[-AIService.SUMMARIZE_THRESHOLD:] if len(db_messages) > AIService.SUMMARIZE_THRESHOLD else db_messages
        for m in recent_messages:
            role = m["role"]
            if role in ("user", "assistant"):
                llm_messages.append({"role": role, "content": m["content"]})
            elif role == "tool_result":
                llm_messages.append({"role": "tool" if ai_service and ai_service.provider in ("openai", "portkey", "custom") else "user", "content": m["content"]})
            elif role == "summary":
                # Already handled above
                pass
            # tool_call messages with rejected status: add a note
            elif role == "tool_call" and m.get("tool_status") == "rejected":
                llm_messages.append({"role": "user", "content": f"[The grader rejected the tool call: {m.get('tool_name', 'unknown')}]"})

        if not ai_service:
            await self.send_json({"type": "chat.error", "message": "AI is not configured for this course."})
            return

        # Prepend editor context to the last user message so the LLM sees it
        if context_prefix:
            for i in range(len(llm_messages) - 1, -1, -1):
                if llm_messages[i]["role"] == "user":
                    llm_messages[i] = {**llm_messages[i], "content": context_prefix + llm_messages[i]["content"]}
                    break

        # Stream from AI
        assistant_text = ""
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0

        try:
            async for chunk in ai_service.chat_stream(llm_messages, ALL_TOOLS):
                chunk_type = chunk.get("type")

                if chunk_type == "thinking":
                    await self.send_json({"type": "chat.thinking"})

                elif chunk_type == "thinking_done":
                    await self.send_json({"type": "chat.thinking_done"})

                elif chunk_type == "token":
                    assistant_text += chunk["content"]
                    await self.send_json({"type": "chat.token", "content": chunk["content"]})

                elif chunk_type == "tool_call":
                    tool_name = chunk["name"]
                    tool_args = chunk.get("args", {})
                    # Default end_line to start_line for comment tools if omitted
                    if tool_name in ("create_inline_comment", "apply_rubric_comment"):
                        if "end_line" not in tool_args and "start_line" in tool_args:
                            tool_args = {**tool_args, "end_line": tool_args["start_line"]}

                    if tool_name in SERVER_SIDE_TOOLS:
                        # Execute immediately, no approval needed
                        result = await execute_server_tool(tool_name, tool_args, self.submission_id)
                        # Save tool_call + tool_result messages
                        tc_msg = await sync_to_async(ChatMessage.objects.create)(
                            conversation=conversation, role='tool_call',
                            content=f"Executing {tool_name}", tool_name=tool_name,
                            tool_args=tool_args, tool_status='approved',
                        )
                        await sync_to_async(ChatMessage.objects.create)(
                            conversation=conversation, role='tool_result',
                            content=result, tool_name=tool_name,
                        )
                        await self.send_json({
                            "type": "chat.tool_result",
                            "message_id": tc_msg.id,
                            "name": tool_name,
                            "result": result,
                        })

                        # Continue conversation with tool result
                        llm_messages.append({"role": "assistant", "content": assistant_text})
                        if ai_service.provider in ("openai", "portkey", "custom"):
                            llm_messages.append({"role": "tool", "content": result, "tool_call_id": chunk.get("id", "")})
                        else:
                            llm_messages.append({"role": "user", "content": f"[Tool Result for {tool_name}]: {result}"})

                        assistant_text = ""
                        # Resume streaming
                        async for resume_chunk in ai_service.chat_stream(llm_messages, ALL_TOOLS):
                            rtype = resume_chunk.get("type")
                            if rtype == "thinking":
                                await self.send_json({"type": "chat.thinking"})
                            elif rtype == "thinking_done":
                                await self.send_json({"type": "chat.thinking_done"})
                            elif rtype == "token":
                                assistant_text += resume_chunk["content"]
                                await self.send_json({"type": "chat.token", "content": resume_chunk["content"]})
                            elif rtype == "tool_call":
                                # Nested tool call — save as pending for client-side
                                await self._save_and_send_tool_call(
                                    conversation, resume_chunk, assistant_text
                                )
                                return
                            elif rtype == "done":
                                input_tokens += resume_chunk.get("input_tokens", 0)
                                output_tokens += resume_chunk.get("output_tokens", 0)
                            elif rtype == "error":
                                await self.send_json({"type": "chat.error", "message": resume_chunk["message"]})
                                return

                    elif tool_name in CLIENT_SIDE_TOOLS:
                        # Requires user approval — save and pause
                        await self._save_and_send_tool_call(conversation, chunk, assistant_text)
                        return
                    else:
                        await self.send_json({"type": "chat.error", "message": f"Unknown tool: {tool_name}"})

                elif chunk_type == "done":
                    input_tokens = chunk.get("input_tokens", 0)
                    output_tokens = chunk.get("output_tokens", 0)
                    cached_tokens = chunk.get("cached_tokens", 0)

                elif chunk_type == "error":
                    await self.send_json({"type": "chat.error", "message": chunk["message"]})
                    return
        except Exception as e:
            logger.error(f"Chat stream failed unexpectedly: {e}", exc_info=True)
            await self.send_json({"type": "chat.error", "message": "An unexpected error occurred. Please try again."})
            return

        # Save assistant message
        if assistant_text:
            await sync_to_async(ChatMessage.objects.create)(
                conversation=conversation, role='assistant', content=assistant_text,
                token_count=output_tokens,
            )

        # Record usage
        if ai_service and (input_tokens or output_tokens):
            from core.services.ai_service import GenerationResult
            result = GenerationResult(
                text=assistant_text, success=True,
                input_tokens=input_tokens, output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cached_tokens=cached_tokens,
            )
            await sync_to_async(ai_service.record_usage)(result, self.user, request_type='chat')

        await self.send_json({
            "type": "chat.done",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

    async def _save_and_send_tool_call(self, conversation, chunk: dict, assistant_text: str):
        """Save a client-side tool call as pending and send it to the client for approval."""
        from asgiref.sync import sync_to_async
        from core.models import ChatMessage

        # Save assistant text generated so far
        if assistant_text:
            await sync_to_async(ChatMessage.objects.create)(
                conversation=conversation, role='assistant', content=assistant_text,
            )

        # Save the tool call as pending
        description = await self._describe_tool_call(chunk["name"], chunk.get("args", {}))
        tc_msg = await sync_to_async(ChatMessage.objects.create)(
            conversation=conversation, role='tool_call',
            content=description,
            tool_name=chunk["name"],
            tool_args=chunk.get("args", {}),
            tool_status='pending',
        )

        await self.send_json({
            "type": "chat.tool_call",
            "message_id": tc_msg.id,
            "name": chunk["name"],
            "args": chunk.get("args", {}),
            "description": tc_msg.content,
        })

    async def _handle_tool_approve(self, content: dict):
        """User approved a tool call. Execute client-side (acknowledge) or server-side, then resume."""
        from asgiref.sync import sync_to_async
        from core.models import ChatMessage, ChatConversation
        from core.services.chat_tools import CLIENT_SIDE_TOOLS

        message_id = content.get("message_id")
        result_text = content.get("result", "Tool executed successfully.")

        try:
            tc_msg = await sync_to_async(
                lambda: ChatMessage.objects.select_related('conversation').get(
                    pk=message_id, conversation__user=self.user, tool_status='pending'
                )
            )()
        except ChatMessage.DoesNotExist:
            await self.send_json({"type": "chat.error", "message": "Tool call not found or already resolved."})
            return

        # Mark as approved
        tc_msg.tool_status = 'approved'
        await sync_to_async(tc_msg.save)()

        # Save tool result
        await sync_to_async(ChatMessage.objects.create)(
            conversation=tc_msg.conversation, role='tool_result',
            content=result_text, tool_name=tc_msg.tool_name,
        )

        # Resume conversation with the tool result
        await self._resume_after_tool(tc_msg.conversation, tc_msg.tool_name or "", result_text)

    async def _handle_tool_reject(self, content: dict):
        """User rejected a tool call. Notify the AI and resume."""
        from asgiref.sync import sync_to_async
        from core.models import ChatMessage

        message_id = content.get("message_id")
        reason = content.get("reason", "The grader rejected this action.")

        try:
            tc_msg = await sync_to_async(
                lambda: ChatMessage.objects.select_related('conversation').get(
                    pk=message_id, conversation__user=self.user, tool_status='pending'
                )
            )()
        except ChatMessage.DoesNotExist:
            await self.send_json({"type": "chat.error", "message": "Tool call not found or already resolved."})
            return

        tc_msg.tool_status = 'rejected'
        await sync_to_async(tc_msg.save)()

        # Save rejection as tool result
        rejection_text = f"[Rejected by grader]: {reason}"
        await sync_to_async(ChatMessage.objects.create)(
            conversation=tc_msg.conversation, role='tool_result',
            content=rejection_text, tool_name=tc_msg.tool_name,
        )

        # Resume with rejection context
        await self._resume_after_tool(tc_msg.conversation, tc_msg.tool_name or "", rejection_text)

    async def _resume_after_tool(self, conversation, tool_name: str, result_text: str):
        """Resume the AI conversation after a tool call is resolved."""
        from asgiref.sync import sync_to_async
        from core.models import ChatMessage
        from core.services.ai_service import AIService, GenerationResult
        from core.services.chat_tools import ALL_TOOLS, SERVER_SIDE_TOOLS, execute_server_tool

        ai_service = await self._get_ai_service(conversation)
        if not ai_service:
            await self.send_json({"type": "chat.error", "message": "AI is not configured."})
            return

        # Rebuild messages
        system_prompt = await self._build_system_prompt(conversation)
        llm_messages = [{"role": "system", "content": system_prompt}]

        if conversation.summary:
            llm_messages.append({"role": "assistant", "content": f"[Previous conversation summary]: {conversation.summary}"})

        db_messages = await sync_to_async(
            lambda: list(conversation.messages.order_by('created').values('role', 'content', 'tool_name', 'tool_args', 'tool_status'))
        )()

        recent = db_messages[-AIService.SUMMARIZE_THRESHOLD:] if len(db_messages) > AIService.SUMMARIZE_THRESHOLD else db_messages
        for m in recent:
            role = m["role"]
            if role in ("user", "assistant"):
                llm_messages.append({"role": role, "content": m["content"]})
            elif role == "tool_result":
                if ai_service.provider in ("openai", "portkey", "custom"):
                    llm_messages.append({"role": "tool", "content": m["content"]})
                else:
                    llm_messages.append({"role": "user", "content": f"[Tool Result for {m.get('tool_name', '')}]: {m['content']}"})
            elif role == "tool_call" and m.get("tool_status") == "rejected":
                llm_messages.append({"role": "user", "content": f"[Rejected tool: {m.get('tool_name', '')}]"})

        # Stream continuation
        assistant_text = ""
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0

        try:
            async for chunk in ai_service.chat_stream(llm_messages, ALL_TOOLS):
                ctype = chunk.get("type")
                if ctype == "thinking":
                    await self.send_json({"type": "chat.thinking"})
                elif ctype == "thinking_done":
                    await self.send_json({"type": "chat.thinking_done"})
                elif ctype == "token":
                    assistant_text += chunk["content"]
                    await self.send_json({"type": "chat.token", "content": chunk["content"]})
                elif ctype == "tool_call":
                    tn = chunk["name"]
                    ta = chunk.get("args", {})
                    if tn in SERVER_SIDE_TOOLS:
                        result = await execute_server_tool(tn, ta, self.submission_id)
                        tc_msg = await sync_to_async(ChatMessage.objects.create)(
                            conversation=conversation, role='tool_call',
                            content=f"Executing {tn}", tool_name=tn,
                            tool_args=ta, tool_status='approved',
                        )
                        await sync_to_async(ChatMessage.objects.create)(
                            conversation=conversation, role='tool_result',
                            content=result, tool_name=tn,
                        )
                        await self.send_json({"type": "chat.tool_result", "message_id": tc_msg.id, "name": tn, "result": result})
                        # Would need recursive resume here — for simplicity, end turn
                    else:
                        await self._save_and_send_tool_call(conversation, chunk, assistant_text)
                        return
                elif ctype == "done":
                    input_tokens = chunk.get("input_tokens", 0)
                    output_tokens = chunk.get("output_tokens", 0)
                    cached_tokens = chunk.get("cached_tokens", 0)
                elif ctype == "error":
                    await self.send_json({"type": "chat.error", "message": chunk["message"]})
                    return
        except Exception as e:
            logger.error(f"Chat resume stream failed: {e}", exc_info=True)
            await self.send_json({"type": "chat.error", "message": "An unexpected error occurred. Please try again."})
            return

        if assistant_text:
            await sync_to_async(ChatMessage.objects.create)(
                conversation=conversation, role='assistant', content=assistant_text,
                token_count=output_tokens,
            )

        if ai_service and (input_tokens or output_tokens):
            result_obj = GenerationResult(
                text=assistant_text, success=True,
                input_tokens=input_tokens, output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cached_tokens=cached_tokens,
            )
            await sync_to_async(ai_service.record_usage)(result_obj, self.user, request_type='chat')

        await self.send_json({"type": "chat.done", "input_tokens": input_tokens, "output_tokens": output_tokens})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _authenticate(self, token_param: Optional[str]) -> Optional[User]:
        """Authenticate from token query param (JWT or DRF Token)."""
        from asgiref.sync import sync_to_async

        if not token_param:
            return None

        token_param = token_param.strip()
        if not token_param:
            return None

        # Try JWT (token contains dots)
        if "." in token_param:
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication
                jwt_auth = JWTAuthentication()
                # get_validated_token is pure in-memory (no DB)
                validated = jwt_auth.get_validated_token(token_param)  # type: ignore[arg-type]
                # get_user does a DB lookup — must be wrapped
                return await sync_to_async(jwt_auth.get_user)(validated)
            except Exception:
                pass
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication
                jwt_auth = JWTAuthentication()
                validated = jwt_auth.get_validated_token(token_param.encode("utf-8"))
                return await sync_to_async(jwt_auth.get_user)(validated)
            except Exception:
                pass

        # Try DRF Token
        try:
            from rest_framework.authentication import TokenAuthentication
            token_auth = TokenAuthentication()
            user, _ = await sync_to_async(token_auth.authenticate_credentials)(token_param)
            return user
        except Exception:
            pass

        return None

    async def _check_permission(self) -> bool:
        """Check if the user has staff access to the submission."""
        from asgiref.sync import sync_to_async
        from core.models import Submission
        from core.permissions.helpers import isStaffOfSub

        try:
            submission = await sync_to_async(
                lambda: Submission.objects.select_related('assignment__course').get(pk=self.submission_id)
            )()
            return await sync_to_async(isStaffOfSub)(self.user, submission)
        except Submission.DoesNotExist:
            return False

    async def _get_ai_service(self, conversation):
        """Get an AIService instance for the conversation's course."""
        from asgiref.sync import sync_to_async
        from core.services.ai_service import AIService

        def _build_service():
            # All ORM access (course.organization, policy checks) must happen in sync context
            course = conversation.assignment.course
            assignment = conversation.assignment
            service = AIService(course, assignment)
            return service if service.is_configured else None

        try:
            return await sync_to_async(_build_service)()
        except Exception as e:
            logger.warning(f"Failed to create AIService: {e}")
        return None

    async def _build_system_prompt(self, conversation) -> str:
        """Build the system prompt with full submission context."""
        from asgiref.sync import sync_to_async
        from core.services.ai_service import AIService

        ai_service = await self._get_ai_service(conversation)
        if not ai_service:
            return "You are an AI grading assistant."

        assignment = await sync_to_async(lambda: conversation.assignment)()
        submission = await sync_to_async(lambda: conversation.submission)()

        # File list
        files = await sync_to_async(
            lambda: list(submission.files.values_list('id', 'name'))
        )()
        file_list = ", ".join(
            f"{name} (id={fid}, notebook)" if name.endswith('.ipynb')
            else f"{name} (id={fid})"
            for fid, name in files
        )

        # Rubric context
        rubric_lines = []
        categories = await sync_to_async(
            lambda: list(assignment.rubricCategories.prefetch_related('rubricComments').all())
        )()
        for cat in categories:
            comments = await sync_to_async(lambda c=cat: list(c.rubricComments.all()))()
            rubric_lines.append(f"  Category: {cat.name} (max {cat.pointLimit} pts)")
            for rc in comments:
                rubric_lines.append(f"    - [{rc.id}] {rc.text} ({rc.pointDelta:+g} pts)")
        rubric_context = "\n".join(rubric_lines)

        # Existing comments
        from core.models import Comment
        existing = await sync_to_async(
            lambda: list(Comment.objects.filter(file__submission=submission).select_related('file').order_by('file__name', 'startLine'))
        )()
        comment_lines = []
        for c in existing:
            fname = c.file.name if c.file else "?"
            if fname.endswith('.ipynb'):
                location = f"Cell {c.startLine}" if c.startLine == c.endLine else f"Cells {c.startLine}-{c.endLine}"
            else:
                location = f"{c.startLine}-{c.endLine}"
            comment_lines.append(f"  {fname}:{location} ({c.pointDelta:+g}pts): {c.text[:200]}")
        existing_comments = "\n".join(comment_lines)

        return ai_service.build_chat_system_prompt(
            assignment_name=assignment.name,
            submission_id=submission.id,
            file_list=file_list,
            rubric_context=rubric_context,
            existing_comments=existing_comments,
        )

    async def _describe_tool_call(self, tool_name: str, args: dict) -> str:
        """Generate a human-readable description of a tool call for the grader."""
        from asgiref.sync import sync_to_async
        from core.models import SubmissionFile, RubricComment

        async def get_file_name(file_id) -> str:
            if not file_id:
                return "unknown file"
            try:
                name = await sync_to_async(
                    lambda: SubmissionFile.objects.filter(
                        pk=file_id, submission_id=self.submission_id
                    ).values_list('name', flat=True).first()
                )()
                return name or f"file {file_id}"
            except Exception:
                return f"file {file_id}"

        async def get_rubric_comment_text(rc_id) -> str:
            if not rc_id:
                return f"#{rc_id}"
            try:
                text = await sync_to_async(
                    lambda: RubricComment.objects.filter(pk=rc_id).values_list('text', flat=True).first()
                )()
                return f'"{text}"' if text else f"#{rc_id}"
            except Exception:
                return f"#{rc_id}"

        if tool_name == "apply_rubric_comment":
            file_name = await get_file_name(args.get('file_id'))
            rc_text = await get_rubric_comment_text(args.get('rubric_comment_id'))
            return (
                f"Apply rubric comment {rc_text} "
                f"to {file_name} "
                f"at lines {args.get('start_line')}-{args.get('end_line')}"
            )
        elif tool_name == "create_inline_comment":
            file_name = await get_file_name(args.get('file_id'))
            text_preview = (args.get("text") or "")[:80]
            pts = args.get("point_delta", 0)
            return (
                f"Add comment to {file_name} "
                f"lines {args.get('start_line')}-{args.get('end_line')}: "
                f"\"{text_preview}\""
                + (f" ({pts:+g} pts)" if pts else "")
            )
        elif tool_name == "navigate_to_location":
            file_name = await get_file_name(args.get('file_id'))
            return f"Navigate to {file_name} line {args.get('line')}"
        return f"Execute {tool_name} with {json.dumps(args)}"
