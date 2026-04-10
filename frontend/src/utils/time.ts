export const formatTime = (value: string): string => {
  const date = new Date(value);
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  });
};
