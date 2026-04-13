"""
mini_harness/reliability/resilience.py - Retry and fault tolerance mechanisms
"""

import asyncio
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, Set, Type, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# 可恢复的异常类型 - 仅对这些异常进行重试
RETRYABLE_EXCEPTIONS: Set[Type[Exception]] = {
    ConnectionError,
    TimeoutError,
    OSError,
}


class RetryConfig:
    """重试配置"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Optional[Set[Type[Exception]]] = None,
    ):
        """初始化重试配置

        Args:
            max_attempts: 最大重试次数（包括初始尝试）
            initial_delay: 初始延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            exponential_base: 指数退避的底数
            jitter: 是否添加抖动（随机延迟）
            retryable_exceptions: 可重试的异常类型集合
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = (
            retryable_exceptions or RETRYABLE_EXCEPTIONS
        )

    def should_retry(self, exception: Exception) -> bool:
        """判断是否应该重试

        Args:
            exception: 抛出的异常

        Returns:
            True 表示应该重试，False 表示应该立即抛出
        """
        return isinstance(exception, tuple(self.retryable_exceptions))

    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟时间

        Args:
            attempt: 当前尝试次数（从 1 开始）

        Returns:
            延迟时间（秒）
        """
        # 指数退避: initial_delay * (exponential_base ^ (attempt - 1))
        delay = self.initial_delay * (
            self.exponential_base ** (attempt - 1)
        )
        delay = min(delay, self.max_delay)

        # 添加抖动，防止雷鸣羊群效应
        if self.jitter:
            jitter_amount = delay * 0.1  # 10% 的抖动
            delay += random.uniform(0, jitter_amount)

        return delay


class RetryDecorator:
    """重试装饰器 - 支持同步和异步函数"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Optional[Set[Type[Exception]]] = None,
    ):
        """初始化重试装饰器

        Args:
            max_attempts: 最大重试次数
            initial_delay: 初始延迟时间
            max_delay: 最大延迟时间
            exponential_base: 指数退避的底数
            jitter: 是否添加抖动
            retryable_exceptions: 可重试的异常类型集合
        """
        self.config = RetryConfig(
            max_attempts=max_attempts,
            initial_delay=initial_delay,
            max_delay=max_delay,
            exponential_base=exponential_base,
            jitter=jitter,
            retryable_exceptions=retryable_exceptions,
        )

    def __call__(self, func: F) -> F:
        """装饰函数

        Args:
            func: 要装饰的函数

        Returns:
            装饰后的函数
        """
        if asyncio.iscoroutinefunction(func):
            return self._wrap_async(func)  # type: ignore
        else:
            return self._wrap_sync(func)  # type: ignore

    def _wrap_sync(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """包装同步函数"""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(1, self.config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # 判断是否应该重试
                    if not self.config.should_retry(e):
                        raise

                    # 最后一次尝试，不再重试
                    if attempt == self.config.max_attempts:
                        raise

                    # 计算延迟时间并等待
                    delay = self.config.calculate_delay(attempt)
                    time.sleep(delay)

            # 理论上不应该到达这里，但作为保险
            if last_exception:
                raise last_exception

        return wrapper

    def _wrap_async(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """包装异步函数"""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(1, self.config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # 判断是否应该重试
                    if not self.config.should_retry(e):
                        raise

                    # 最后一次尝试，不再重试
                    if attempt == self.config.max_attempts:
                        raise

                    # 计算延迟时间并等待
                    delay = self.config.calculate_delay(attempt)
                    await asyncio.sleep(delay)

            # 理论上不应该到达这里，但作为保险
            if last_exception:
                raise last_exception

        return wrapper


def retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Set[Type[Exception]]] = None,
) -> Callable[[F], F]:
    """便利函数 - 直接使用装饰器

    使用示例:
        @retry(max_attempts=3, initial_delay=1.0)
        async def call_external_api(url: str):
            return await make_http_request(url)

    Args:
        max_attempts: 最大重试次数
        initial_delay: 初始延迟时间
        max_delay: 最大延迟时间
        exponential_base: 指数退避的底数
        jitter: 是否添加抖动
        retryable_exceptions: 可重试的异常类型集合

    Returns:
        装饰器
    """
    return RetryDecorator(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retryable_exceptions=retryable_exceptions,
    )


class CircuitBreaker:
    """熔断器 - 防止故障级联

    当错误率过高时，暂时停止调用，给系统恢复时间。
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        """初始化熔断器

        Args:
            failure_threshold: 失败次数阈值，超过则打开熔断器
            recovery_timeout: 恢复超时时间（秒）
            expected_exception: 期望的异常类型
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.is_open = False

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """通过熔断器调用函数

        Args:
            func: 要调用的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            RuntimeError: 当熔断器打开时
            Exception: 来自被调用函数的异常
        """
        # 检查是否应该关闭熔断器
        if self.is_open:
            now = time.time()
            if (
                self.last_failure_time
                and now - self.last_failure_time >= self.recovery_timeout
            ):
                # 恢复尝试
                self.is_open = False
                self.failure_count = 0
            else:
                raise RuntimeError("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)
            # 成功调用，重置失败计数
            self.failure_count = 0
            return result
        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.is_open = True

            raise
